import re
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import activity, database
from app.config import settings
from app.database import get_db
from app.deps import get_admin_user, get_current_user
from app.models import Subscription, SystemSetting, User
from app.schemas import RegistrationSettingsIn, ReminderScanTimeIn
from app.services import scheduler
from app.services.system_settings import (
    REGISTRATION_ENABLED_KEY,
    REQUIRE_ADMIN_APPROVAL_KEY,
    get_bool,
    set_bool,
)

router = APIRouter(prefix="/api/system", tags=["system"])

APP_VERSION = "1.11.2"
GITHUB_REPO = "suyijun8182/easysub"
_REMINDER_SCAN_TIME_KEY = "reminder_scan_time"


def _registration_settings(db: Session) -> dict[str, bool]:
    return {
        "registration_enabled": get_bool(db, REGISTRATION_ENABLED_KEY, True),
        "require_admin_approval": get_bool(
            db, REQUIRE_ADMIN_APPROVAL_KEY, settings.require_admin_approval
        ),
    }

# 版本检查结果缓存（避免频繁请求 GitHub，未认证限流 60 次/小时）
_ver_cache: dict = {"at": 0.0, "data": None}
_VER_TTL = 6 * 3600


def _parse_semver(v: str):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def _fetch_latest() -> dict:
    """从 GitHub tags 取最新版本号。失败则返回仅含当前版本的结果。"""
    result = {
        "current": APP_VERSION,
        "latest": None,
        "update_available": False,
        "release_url": f"https://github.com/{GITHUB_REPO}/releases",
        "error": None,
    }
    try:
        with httpx.Client(timeout=8, headers={"Accept": "application/vnd.github+json"}) as c:
            r = c.get(f"https://api.github.com/repos/{GITHUB_REPO}/tags", params={"per_page": 30})
            r.raise_for_status()
            versions = []
            for tag in r.json():
                sv = _parse_semver(tag.get("name", ""))
                if sv:
                    versions.append((sv, tag["name"]))
            if versions:
                versions.sort(reverse=True)
                latest_tuple, latest_name = versions[0]
                result["latest"] = latest_name.lstrip("v")
                cur = _parse_semver(APP_VERSION) or (0, 0, 0)
                result["update_available"] = latest_tuple > cur
                result["release_url"] = f"https://github.com/{GITHUB_REPO}/releases/tag/{latest_name}"
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}"
    return result


@router.get("/version-check")
def version_check(refresh: bool = False, user: User = Depends(get_current_user)):
    """检查是否有新版本（对比 GitHub 最新 tag）。结果缓存 6 小时。"""
    now = time.monotonic()
    if refresh or not _ver_cache["data"] or (now - _ver_cache["at"]) > _VER_TTL:
        _ver_cache["data"] = _fetch_latest()
        _ver_cache["at"] = now
    return {**_ver_cache["data"], "checked_at": datetime.now().isoformat(timespec="seconds")}


@router.get("/info")
def info(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    your_total = db.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.user_id == user.id)
    )
    your_active = db.scalar(
        select(func.count())
        .select_from(Subscription)
        .where(Subscription.user_id == user.id, Subscription.is_active.is_(True))
    )
    data = {
        "version": APP_VERSION,
        "db_configured": database.is_configured(),
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "timezone": settings.tz,
        "reminder_scan_time": scheduler.reminder_scan_time(),
        "your_subscriptions": your_total,
        "your_active": your_active,
        "telegram_enabled": user.telegram_enabled,
    }
    if user.is_admin:
        data["total_users"] = db.scalar(select(func.count()).select_from(User))
        data["total_subscriptions"] = db.scalar(select(func.count()).select_from(Subscription))
    return data


@router.put("/reminder-scan-time")
def update_reminder_scan_time(
    payload: ReminderScanTimeIn,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """管理员更新全局提醒扫描时间，并立即重排本进程的定时任务。"""
    try:
        value = scheduler.normalize_reminder_scan_time(payload.reminder_scan_time)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    row = db.get(SystemSetting, _REMINDER_SCAN_TIME_KEY)
    if row is None:
        db.add(SystemSetting(key=_REMINDER_SCAN_TIME_KEY, value=value))
    else:
        row.value = value
    db.commit()

    scheduler.reschedule_reminder_scans(value)
    activity.log("system.reminder_scan_time", f"提醒扫描时间更新为 {value}", user=user)
    return {"reminder_scan_time": value}


@router.get("/registration")
def registration_status(db: Session = Depends(get_db)):
    """Public status used by the login screen; registration is still enforced by auth."""
    return {"registration_enabled": _registration_settings(db)["registration_enabled"]}


@router.get("/registration-settings")
def get_registration_settings(
    user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    return _registration_settings(db)


@router.put("/registration-settings")
def update_registration_settings(
    payload: RegistrationSettingsIn,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    set_bool(db, REGISTRATION_ENABLED_KEY, payload.registration_enabled)
    set_bool(db, REQUIRE_ADMIN_APPROVAL_KEY, payload.require_admin_approval)
    db.commit()
    activity.log(
        "system.registration_settings",
        "注册设置已更新："
        f"允许注册={'是' if payload.registration_enabled else '否'}，"
        f"需审核={'是' if payload.require_admin_approval else '否'}",
        user=user,
    )
    return _registration_settings(db)
