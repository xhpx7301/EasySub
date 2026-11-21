import html
import os
import re
import threading
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import activity, database, icon_library
from app.database import get_db
from app.deps import get_admin_user, get_current_user
from app.models import IconLibraryItem, User

router = APIRouter(prefix="/api/icons", tags=["icons"])

UPLOAD_DIR = os.path.join("data", "icons")
LIBRARY_DIR = os.path.join("data", "icons", "library")
ALLOWED = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".ico"}
MAX_BYTES = 2 * 1024 * 1024  # 2MB
# 镜像与源码中内置的服务图标目录（构建时从 frontend/public/preview-icons 复制到 frontend_dist）
BUNDLED_DIRS = (
    os.path.join("frontend_dist", "preview-icons"),
    os.path.join("..", "frontend", "public", "preview-icons"),
)
FETCH_TIMEOUT = 4
FAILURE_TTL = 6 * 3600
PLACEHOLDER_HEADERS = {
    "Cache-Control": "public, max-age=86400",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
}
_failed: dict[str, float] = {}
_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _favicon_client() -> httpx.Client:
    """复用单个 httpx.Client，避免每次请求重复加载 CA 证书拖慢响应。"""
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True)
        return _client


def _fetch_favicon(domain: str) -> bytes:
    resp = _favicon_client().get(f"https://www.google.com/s2/favicons?domain={domain}&sz=64")
    resp.raise_for_status()
    return resp.content


def placeholder_svg(name: str) -> str:
    letter = html.escape((name or "?").strip()[:1].upper() or "?")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="14" fill="#eef0ff"/>'
        f'<text x="32" y="43" text-anchor="middle" fill="#5b5bd6" font-size="34" font-family="sans-serif">{letter}</text>'
        "</svg>"
    )


def _contained(directory: str, name: str) -> str | None:
    root = os.path.realpath(directory)
    candidate = os.path.realpath(os.path.join(root, name))
    try:
        inside = os.path.commonpath([root, candidate]) == root
    except ValueError:
        return None
    return candidate if inside and os.path.isfile(candidate) else None


class IconUrlIn(BaseModel):
    url: str


class IconItemIn(BaseModel):
    name: str
    domain: str | None = None
    category: str = "other"
    icon_url: str
    is_enabled: bool = True
    global_item: bool = False


def _item_out(item: IconLibraryItem, user: User | None = None) -> dict:
    return {
        "id": item.id,
        "slug": item.slug,
        "name": item.name,
        "domain": item.domain or "",
        "category": item.category,
        "category_label": dict(icon_library.CATEGORY_LABELS).get(item.category, item.category),
        "website": f"https://{item.domain}" if item.domain else "",
        "icon": item.icon_url,
        "icon_url": item.icon_url,
        "is_global": item.user_id is None,
        "is_builtin": item.is_builtin,
        "is_enabled": item.is_enabled,
        "can_edit": bool(user and (user.is_admin or item.user_id == user.id)),
    }


@router.post("/upload")
async def upload_icon(
    file: UploadFile = File(...),
    library_name: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户上传本地图标；传入名称时同时保存到个人图标库。"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"不支持的图标格式：{ext}")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "图标过大（上限 2MB）")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_.\-]", "", f"{user.id}_{uuid.uuid4().hex}{ext}")
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    url = f"/static/icons/{name}"

    # 订阅页会传入服务名称，让上传的图标立刻成为可复用、可编辑的个人图标。
    item = None
    display_name = (library_name or "").strip()
    if display_name:
        item = IconLibraryItem(
            user_id=user.id,
            slug=f"custom-{user.id}-{uuid.uuid4().hex}",
            name=display_name[:128],
            category="other",
            icon_url=url,
            is_builtin=False,
            is_enabled=True,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        activity.log("icon.create", f"新增个人图标「{item.name}」", user=user)
    return {"url": url, "item": _item_out(item, user) if item else None}


@router.post("/from-url")
def import_from_url(payload: IconUrlIn, user: User = Depends(get_current_user)):
    """从 URL 下载图标并保存到本地。"""
    url = payload.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "请输入 http(s) 图标地址")
    content = bytearray()
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                for chunk in resp.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise HTTPException(400, "图标过大（上限 2MB）")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"下载失败：{type(e).__name__}")
    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/x-icon": ".ico",
        "image/vnd.microsoft.icon": ".ico",
    }.get(ctype.split(";")[0].strip(), os.path.splitext(url)[1].lower() or ".png")
    if ext not in ALLOWED:
        ext = ".png"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{user.id}_{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(bytes(content))
    return {"url": f"/static/icons/{name}"}


@router.get("/library")
def list_library(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """返回启用中的全局图标和当前用户自己的图标。"""
    rows = db.scalars(
        select(IconLibraryItem)
        .where(
            IconLibraryItem.is_enabled.is_(True),
            or_(IconLibraryItem.user_id.is_(None), IconLibraryItem.user_id == user.id),
        )
        .order_by(IconLibraryItem.user_id.asc(), IconLibraryItem.sort.asc(), IconLibraryItem.name.asc())
    ).all()
    return [_item_out(row, user) for row in rows]


@router.get("/manage")
def manage_library(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """返回图标管理页可见的全局图标和个人图标。"""
    rows = db.scalars(
        select(IconLibraryItem)
        .where(or_(IconLibraryItem.user_id.is_(None), IconLibraryItem.user_id == user.id))
        .order_by(IconLibraryItem.user_id.asc(), IconLibraryItem.sort.asc(), IconLibraryItem.name.asc())
    ).all()
    return {
        "items": [_item_out(row, user) for row in rows],
        "categories": [{"key": key, "label": label} for key, label in icon_library.CATEGORY_LABELS]
        + [{"key": "other", "label": "其它 / Other"}],
    }


@router.post("/manage")
def create_library_item(
    payload: IconItemIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    icon_url = payload.icon_url.strip()
    if not name or not icon_url:
        raise HTTPException(400, "名称和图标地址不能为空")
    if payload.global_item and not user.is_admin:
        raise HTTPException(403, "只有管理员可以新增全局图标")
    slug = f"custom-{user.id}-{uuid.uuid4().hex}"
    row = IconLibraryItem(
        user_id=None if payload.global_item else user.id,
        slug=slug,
        name=name[:128],
        domain=(payload.domain or "").strip()[:255] or None,
        category=(payload.category or "other").strip()[:64] or "other",
        icon_url=icon_url[:512],
        is_builtin=False,
        is_enabled=payload.is_enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    activity.log("icon.create", f"新增{'全局' if row.user_id is None else '个人'}图标「{row.name}」", user=user)
    return _item_out(row, user)


@router.put("/manage/{item_id}")
def update_library_item(
    item_id: int,
    payload: IconItemIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(IconLibraryItem, item_id)
    if not row or (row.user_id is not None and row.user_id != user.id) or (row.user_id is None and not user.is_admin):
        raise HTTPException(404, "图标不存在或无权修改")
    if payload.global_item != (row.user_id is None):
        raise HTTPException(400, "不能在编辑时切换图标归属")
    name = payload.name.strip()
    icon_url = payload.icon_url.strip()
    if not name or not icon_url:
        raise HTTPException(400, "名称和图标地址不能为空")
    row.name = name[:128]
    row.domain = (payload.domain or "").strip()[:255] or None
    row.category = (payload.category or "other").strip()[:64] or "other"
    row.icon_url = icon_url[:512]
    row.is_enabled = payload.is_enabled
    db.commit()
    activity.log("icon.update", f"更新图标「{row.name}」", user=user)
    return _item_out(row, user)


@router.delete("/manage/{item_id}")
def delete_library_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(IconLibraryItem, item_id)
    if not row or (row.user_id is not None and row.user_id != user.id) or (row.user_id is None and not user.is_admin):
        raise HTTPException(404, "图标不存在或无权删除")
    name = row.name
    db.delete(row)
    db.commit()
    activity.log("icon.delete", f"删除图标「{name}」", user=user, level="warn")
    return {"ok": True}


@router.get("/library/{slug}")
def library_icon(slug: str):
    """返回商家图标：自定义地址 → 本地缓存 → 镜像内置图标 → 联网下载；失败返回可缓存的首字母占位图。"""
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "", slug)
    if not safe.endswith(".png"):
        safe += ".png"
    db_row = None
    if database.SessionLocal is not None:
        db = database.SessionLocal()
        try:
            db_row = db.scalar(
                select(IconLibraryItem).where(IconLibraryItem.slug == safe.removesuffix(".png"))
            )
        finally:
            db.close()
    if (
        db_row
        and db_row.icon_url.startswith(("/static/", "http://", "https://"))
        and not db_row.icon_url.startswith("/api/icons/library/")
    ):
        return RedirectResponse(db_row.icon_url)

    for directory in (LIBRARY_DIR, *BUNDLED_DIRS):
        found = _contained(directory, safe)
        if found:
            return FileResponse(found)

    domain = (db_row.domain if db_row else None) or icon_library.domain_for_slug(safe)
    if not domain:
        raise HTTPException(404, "未知图标")

    display_name = db_row.name if db_row else None
    if not display_name:
        entry = next((e for e in icon_library.manifest() if e["domain"] == domain), None)
        display_name = entry["name"] if entry else domain
    placeholder = Response(
        content=placeholder_svg(display_name),
        media_type="image/svg+xml",
        headers=PLACEHOLDER_HEADERS,
    )

    failed_at = _failed.get(safe)
    if failed_at is not None and time.monotonic() - failed_at < FAILURE_TTL:
        return placeholder

    # 联网抓取（大陆环境可能不可达，因此超时 4s 且失败 6 小时内不再重试）
    try:
        content = _fetch_favicon(domain)
    except Exception:  # noqa: BLE001
        _failed[safe] = time.monotonic()
        return placeholder

    _failed.pop(safe, None)
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    with open(os.path.join(LIBRARY_DIR, safe), "wb") as f:
        f.write(content)
    return Response(content=content, media_type="image/png")
