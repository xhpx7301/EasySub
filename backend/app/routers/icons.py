import os
import re
import uuid

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
async def upload_icon(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """用户上传本地图标。"""
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
    return {"url": f"/static/icons/{name}"}


@router.post("/from-url")
def import_from_url(payload: IconUrlIn, user: User = Depends(get_current_user)):
    """从 URL 下载图标并保存到本地。"""
    url = payload.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "请输入 http(s) 图标地址")
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"下载失败：{e}")
    if len(resp.content) > MAX_BYTES:
        raise HTTPException(400, "图标过大（上限 2MB）")
    ctype = resp.headers.get("content-type", "")
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
        f.write(resp.content)
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
    """返回某个商家图标；本地无缓存时从公共 favicon 服务下载后缓存。"""
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "", slug)
    if not safe.endswith(".png"):
        safe += ".png"
    db_row = None
    if database.SessionLocal is not None:
        db = database.SessionLocal()
        try:
            db_row = db.scalar(select(IconLibraryItem).where(IconLibraryItem.slug == safe.removesuffix(".png")))
        finally:
            db.close()
    if db_row and db_row.icon_url.startswith(("/static/", "http://", "https://")) and not db_row.icon_url.startswith("/api/icons/library/"):
        return RedirectResponse(db_row.icon_url)
    path = os.path.join(LIBRARY_DIR, safe)
    if os.path.isfile(path):
        return FileResponse(path)

    domain = (db_row.domain if db_row else None) or icon_library.domain_for_slug(safe)
    if not domain:
        raise HTTPException(404, "未知图标")
    # 用 Google favicon 服务抓取该商家图标（覆盖面广、稳定）
    fav = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
    try:
        resp = httpx.get(fav, timeout=12, follow_redirects=True)
        resp.raise_for_status()
        os.makedirs(LIBRARY_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(resp.content)
        return Response(content=resp.content, media_type="image/png")
    except Exception:  # noqa: BLE001
        # 下载失败返回 1x1 透明占位，避免前端报错
        raise HTTPException(404, "图标暂不可用")
