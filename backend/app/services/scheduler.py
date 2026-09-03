"""订阅到期、提醒、自动续费及维护任务。"""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app import activity, database
from app.billing import add_cycle
from app.config import settings
from app.models import Category, NotificationLog, PaymentMethod, Subscription, SystemSetting, User
from app.services import exchange, notify

_scheduler: BackgroundScheduler | None = None
_reminder_scan_time: str | None = None
_REMINDER_SCAN_TIME_KEY = "reminder_scan_time"


def _parse_days(raw: str) -> list[int]:
    out = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def normalize_reminder_scan_time(value: str) -> str:
    """验证 HH:MM 格式并规范化为零填充形式。"""
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except (TypeError, ValueError) as e:
        raise ValueError("提醒扫描时间必须为 HH:MM 格式") from e


def reminder_scan_time() -> str:
    """返回当前生效的扫描时间；环境变量只作为首次运行的默认值。"""
    if _reminder_scan_time:
        return _reminder_scan_time
    try:
        return normalize_reminder_scan_time(settings.reminder_scan_time)
    except ValueError:
        return "09:00"


def _scan_time() -> time:
    hour, minute = (int(x) for x in reminder_scan_time().split(":"))
    return time(hour=hour, minute=minute)


def _load_reminder_scan_time() -> str:
    """从系统设置恢复扫描时间；数据库不可用时回退到环境变量。"""
    if database.SessionLocal is not None:
        db = database.SessionLocal()
        try:
            row = db.get(SystemSetting, _REMINDER_SCAN_TIME_KEY)
            if row:
                return normalize_reminder_scan_time(row.value)
        except Exception:  # noqa: BLE001
            pass
        finally:
            db.close()
    return reminder_scan_time()


def reschedule_reminder_scans(value: str) -> str:
    """立即让已运行的每日和小时提醒任务使用新的扫描时间。"""
    global _reminder_scan_time
    normalized = normalize_reminder_scan_time(value)
    _reminder_scan_time = normalized
    if _scheduler is not None:
        hour, minute = (int(part) for part in normalized.split(":"))
        _scheduler.reschedule_job(
            "daily_due_tasks", trigger=CronTrigger(hour=hour, minute=minute)
        )
        _scheduler.reschedule_job(
            "hourly_reminder_scan", trigger=CronTrigger(minute=minute)
        )
    return normalized


def _reminder_rules(sub: Subscription) -> list[dict]:
    """规范化新版规则；旧版逗号字段继续按“到期前 N 天”解释。"""
    raw = sub.reminder_rules
    if isinstance(raw, list):
        rules = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            timing = item.get("timing")
            unit = item.get("unit")
            if timing not in {"before", "due", "after"} or unit not in {"day", "hour"}:
                continue
            try:
                value = max(1, int(item.get("value", 1)))
            except (TypeError, ValueError):
                value = 1
            if timing == "due":
                value, unit = 0, "day"
            rule_id = str(item.get("id") or f"rule-{index}")[:48]
            rules.append({
                "id": rule_id,
                "enabled": bool(item.get("enabled", True)),
                "timing": timing,
                "value": value,
                "unit": unit,
            })
        return rules

    rules = []
    for days in _parse_days(sub.remind_days_before):
        rules.append({
            "id": f"legacy-{days}",
            "enabled": True,
            "timing": "due" if days == 0 else "before",
            "value": 0 if days == 0 else days,
            "unit": "day",
        })
    return rules


def _rule_label(rule: dict) -> str:
    if rule["timing"] == "due":
        return "到期当天"
    unit = "天" if rule["unit"] == "day" else "小时"
    if rule["timing"] == "before":
        return f"到期前 {rule['value']} {unit}"
    return f"到期后 {rule['value']} {unit}"


def _already_sent(db, sub_id: int, days_before: int, on_day: date) -> bool:
    """兼容新版启用前已写入的旧提醒日志。"""
    rows = db.scalars(
        select(NotificationLog).where(
            NotificationLog.subscription_id == sub_id,
            NotificationLog.days_before == days_before,
            NotificationLog.event_key.is_(None),
            NotificationLog.status == "sent",
        )
    ).all()
    return any(r.sent_at and r.sent_at.date() == on_day for r in rows)


def _event_sent(db, sub_id: int, event_key: str) -> bool:
    return db.scalar(
        select(NotificationLog.id).where(
            NotificationLog.subscription_id == sub_id,
            NotificationLog.event_key == event_key,
            NotificationLog.status == "sent",
        ).limit(1)
    ) is not None


def _rule_event(sub: Subscription, rule: dict, now: datetime) -> tuple[str, bool]:
    """返回 (事件唯一键, 当前扫描是否应发送)。"""
    due = sub.next_renewal_date
    if not due:
        return "", False
    prefix = f"renewal:{due.isoformat()}:{rule['id']}"
    timing, unit, value = rule["timing"], rule["unit"], rule["value"]
    days_left = (due - now.date()).days

    if timing == "due":
        return prefix, unit == "day" and days_left == 0
    if timing == "before" and unit == "day":
        return prefix, days_left == value
    if timing == "after" and unit == "day":
        days_after = -days_left
        return prefix, days_after == value

    due_at = datetime.combine(due, _scan_time())
    if timing == "before":
        seconds_left = (due_at - now).total_seconds()
        return prefix, 0 < seconds_left <= value * 3600
    seconds_after = (now - due_at).total_seconds()
    return prefix, seconds_after >= value * 3600


def run_auto_renewals(today: date | None = None) -> dict:
    """推进已开启自动续费的到期订阅。

    EasySub 无法替用户向服务商或支付平台扣费；这里的“自动续费”表示在
    预期自动扣款日到达后，自动维护本地的下次续费日期。若服务在到期日停机，
    恢复后会按原账期连续推进，避免把已经自动续费的项目长期显示为过期。
    """
    if database.SessionLocal is None:
        return {"renewed": 0, "skipped": "数据库未配置"}

    today = today or date.today()
    renewed: list[tuple[str, date, date, int, str]] = []
    db = database.SessionLocal()
    try:
        subs = db.scalars(
            select(Subscription).where(
                Subscription.is_active.is_(True),
                Subscription.auto_renew.is_(True),
                Subscription.billing_type == "recurring",
                Subscription.next_renewal_date.is_not(None),
                Subscription.next_renewal_date <= today,
            )
        ).all()
        for sub in subs:
            old_due = sub.next_renewal_date
            next_due = old_due
            # 按原到期日推进，保留月初、月末等原始账期锚点；同时补偿停机期间
            # 错过的多个周期。add_cycle 至少前进一个周期，因此循环必然收敛。
            for _ in range(100_000):
                next_due = add_cycle(next_due, sub.cycle, sub.cycle_count)
                if next_due > today:
                    break
            else:
                raise RuntimeError(f"自动续费日期推进超出安全上限：订阅 {sub.id}")

            sub.next_renewal_date = next_due
            user = db.get(User, sub.user_id)
            if user:
                renewed.append((sub.name, old_due, next_due, user.id, user.username))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # 自动续费是账期记录更新，不伪造实际付款日期；单独写活动日志以便审计。
    for name, old_due, next_due, user_id, username in renewed:
        activity.log(
            "subscription.auto_renew",
            f"自动续费记录「{name}」：下次续费 {old_due} -> {next_due}",
            user=SimpleNamespace(id=user_id, username=username),
        )
    return {"renewed": len(renewed)}


def run_reminder_scan(unit: str = "day", now: datetime | None = None) -> dict:
    """扫描指定单位的提醒规则。天规则每天执行，小时规则每小时执行。"""
    if unit not in {"day", "hour"}:
        raise ValueError(f"未知提醒单位：{unit}")
    now = now or datetime.now()
    today = now.date()
    sent, failed = 0, 0
    if database.SessionLocal is None:
        return {"sent": 0, "failed": 0, "skipped": "数据库未配置"}
    db = database.SessionLocal()
    try:
        subs = db.scalars(
            select(Subscription).where(
                Subscription.is_active.is_(True),
                Subscription.billing_type == "recurring",
                Subscription.next_renewal_date.is_not(None),
            )
        ).all()
        for sub in subs:
            user = db.get(User, sub.user_id)
            if not user:
                continue
            # 只要启用了任意一个通知渠道即发送
            cfg = notify.load_config(user)
            if not any(cfg.get(c, {}).get("enabled") for c in notify.CHANNELS):
                continue
            days_left = (sub.next_renewal_date - today).days
            # 免打扰时段：非紧急（>=2 天）提醒暂缓，紧急（今天/明天）仍照常发；
            # 暂缓的提醒不写已发记录，次日扫描会再次评估。
            if days_left >= 2 and notify.in_quiet_hours(user):
                continue
            for rule in _reminder_rules(sub):
                if not rule["enabled"] or rule["unit"] != unit:
                    continue
                # 自动续费会在当天提醒之后顺延账期，逾期提醒仅适用于手动续费项目。
                if rule["timing"] == "after" and sub.auto_renew:
                    continue
                event_key, should_send = _rule_event(sub, rule, now)
                legacy_sent = (
                    unit == "day"
                    and rule["timing"] in {"before", "due"}
                    and _already_sent(db, sub.id, rule["value"], today)
                )
                if not should_send or _event_sent(db, sub.id, event_key) or legacy_sent:
                    continue
                label = _rule_label(rule)
                text_md = _build_text(db, sub, user, days_left, reminder_label=label)
                subject = f"续费提醒：{sub.name}"
                results = notify.dispatch(
                    user, subject, notify._strip_md(text_md), text_md=text_md
                )
                ok_ch = [r["channel"] for r in results if r.get("ok")]
                err = [f"{r['channel']}: {r['error']}" for r in results if not r.get("ok")]
                if len(ok_ch) == 1:
                    ch_label = ok_ch[0]
                elif ok_ch:
                    ch_label = f"multi:{len(ok_ch)}"
                else:
                    ch_label = "none"
                log = NotificationLog(
                    subscription_id=sub.id,
                    user_id=user.id,
                    days_before=rule["value"] if rule["timing"] == "before" and unit == "day" else 0,
                    event_key=event_key,
                    rule_label=label,
                    channel=ch_label,
                    status="sent" if ok_ch else "failed",
                    message=text_md if ok_ch else "; ".join(err) or "无可用渠道",
                    sent_at=datetime.utcnow(),
                )
                db.add(log)
                if ok_ch:
                    sent += 1
                    activity.log(
                        "notify.reminder",
                        f"已提醒「{sub.name}」（{label}，渠道：{', '.join(ok_ch)}）",
                        user=user,
                    )
                if err:
                    failed += 1
                    activity.log(
                        "notify.reminder",
                        f"提醒「{sub.name}」部分渠道失败：{'; '.join(err)}",
                        user=user,
                        level="error" if not ok_ch else "warn",
                    )
        db.commit()
    finally:
        db.close()
    return {"sent": sent, "failed": failed}


def run_due_tasks() -> dict:
    """串行执行每日到期处理，让当天提醒在自动续费顺延前发出。"""
    return {
        "reminders": run_reminder_scan(),
        "hourly_reminders": run_reminder_scan(unit="hour"),
        "auto_renewals": run_auto_renewals(),
        "date_reminders": run_date_reminders(),
    }


def run_hourly_reminder_scan() -> dict:
    """每小时执行小时规则；每日主任务所在小时交由主任务处理，避免并发。"""
    now = datetime.now()
    if now.hour == _scan_time().hour:
        return {"sent": 0, "failed": 0, "skipped": "由每日任务处理"}
    return run_reminder_scan(unit="hour", now=now)


def run_date_reminders() -> dict:
    """试用期结束 / 取消截止 / 付款卡到期 提醒（每日检查）。

    用 NotificationLog.days_before 的哨兵值区分类型并去重：-1 试用、-2 取消、-3 卡到期。
    """
    if database.SessionLocal is None:
        return {"sent": 0, "skipped": "数据库未配置"}
    today = date.today()
    sent = 0
    db = database.SessionLocal()
    try:
        subs = db.scalars(select(Subscription).where(Subscription.is_active.is_(True))).all()
        for sub in subs:
            user = db.get(User, sub.user_id)
            if not user:
                continue
            cfg = notify.load_config(user)
            if not any(cfg.get(c, {}).get("enabled") for c in notify.CHANNELS):
                continue
            events = []  # (code, subject, text)
            if sub.trial_end:
                d = (sub.trial_end - today).days
                if d in (3, 1, 0):
                    when = "今天" if d == 0 else f"还有 {d} 天"
                    events.append((-1, f"试用将结束：{sub.name}",
                                   f"「{sub.name}」的免费试用{when}结束（{sub.trial_end}）。"
                                   f"如不想被自动扣费，请及时取消或确认转正。"))
            if sub.cancel_by:
                d = (sub.cancel_by - today).days
                if d in (3, 1, 0):
                    when = "今天" if d == 0 else f"还有 {d} 天"
                    events.append((-2, f"取消截止：{sub.name}",
                                   f"「{sub.name}」的取消截止日{when}到（{sub.cancel_by}）。"
                                   f"若要取消请在此之前操作。"))
            if sub.card_expiry:
                exp = _card_expiring(sub.card_expiry, today)
                if exp:
                    tail = f"（尾号 {sub.card_last4}）" if sub.card_last4 else ""
                    events.append((-3, f"付款卡将到期：{sub.name}",
                                   f"「{sub.name}」绑定的付款卡{tail}将于 {sub.card_expiry} 到期，"
                                   f"请及时更换，避免自动续费失败。"))
            for code, subject, body in events:
                if _already_sent(db, sub.id, code, today):
                    continue
                results = notify.dispatch(user, subject, body)
                ok_ch = [r["channel"] for r in results if r.get("ok")]
                db.add(NotificationLog(
                    subscription_id=sub.id, user_id=user.id, days_before=code,
                    channel=(ok_ch[0] if len(ok_ch) == 1 else f"multi:{len(ok_ch)}") if ok_ch else "none",
                    status="sent" if ok_ch else "failed", message=body,
                    sent_at=datetime.utcnow(),
                ))
                if ok_ch:
                    sent += 1
        db.commit()
    finally:
        db.close()
    return {"sent": sent}


def _card_expiring(mmyy: str, today: date) -> bool:
    """卡有效期 MM/YY，若在本月或下月到期则返回 True。"""
    try:
        mm, yy = mmyy.replace(" ", "").split("/")
        m, y = int(mm), 2000 + int(yy) if len(yy) == 2 else int(yy)
        exp_last = date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
        # 到期月的月末 = 下月1号前一天
        from datetime import timedelta
        exp_last = exp_last - timedelta(days=1)
        days = (exp_last - today).days
        return 0 <= days <= 45
    except Exception:  # noqa: BLE001
        return False


def run_weekly_digest() -> dict:
    """每周汇总：把即将续费/已过期的订阅汇总成一条消息推送（按用户设置的星期几）。"""
    if database.SessionLocal is None:
        return {"sent": 0, "skipped": "数据库未配置"}
    today = date.today()
    weekday = today.weekday()  # 0=周一
    sent = 0
    db = database.SessionLocal()
    try:
        users = db.scalars(select(User).where(User.is_active.is_(True))).all()
        for user in users:
            st = user.notify_settings or {}
            if not st.get("digest_enabled"):
                continue
            if int(st.get("digest_weekday", 0)) != weekday:
                continue
            cfg = notify.load_config(user)
            if not any(cfg.get(c, {}).get("enabled") for c in notify.CHANNELS):
                continue
            subs = db.scalars(select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.is_active.is_(True),
                Subscription.billing_type == "recurring",
                Subscription.next_renewal_date.is_not(None),
            )).all()
            upcoming = sorted(
                [s for s in subs if 0 <= (s.next_renewal_date - today).days <= 30],
                key=lambda s: s.next_renewal_date,
            )
            overdue = [s for s in subs if (s.next_renewal_date - today).days < 0]
            if not upcoming and not overdue:
                continue
            lines = ["📅 *本周订阅汇总*", ""]
            if overdue:
                lines.append(f"⚠️ 已过期 {len(overdue)} 项：")
                for s in overdue[:10]:
                    lines.append(f"· {_escape_md(s.name)}（{s.next_renewal_date}）")
                lines.append("")
            if upcoming:
                lines.append(f"🔔 未来 30 天将续费 {len(upcoming)} 项：")
                for s in upcoming[:15]:
                    dleft = (s.next_renewal_date - today).days
                    lines.append(f"· {_escape_md(s.name)} — {s.next_renewal_date}（{dleft} 天，{s.amount:.2f} {s.currency}）")
            text_md = "\n".join(lines)
            notify.dispatch(user, "本周订阅汇总", _strip_md_local(text_md), text_md=text_md, event="digest")
            sent += 1
    finally:
        db.close()
    return {"sent": sent}


def _strip_md_local(text: str) -> str:
    return notify._strip_md(text)


_CYCLE_CN = {"day": "天", "week": "周", "month": "个月", "year": "年"}


def _escape_md(text: str) -> str:
    """转义 Markdown 中可能破坏排版的下划线/星号，保证名称等原样显示。"""
    if not text:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def _build_text(
    db, sub: Subscription, user: User, days_left: int, reminder_label: str | None = None
) -> str:
    """构造一条信息完整、措辞友好的续费提醒。"""
    amount = f"{sub.amount:.2f} {sub.currency}"
    in_base = exchange.convert(db, sub.amount, sub.currency, user.base_currency)
    base_str = ""
    if abs(in_base - sub.amount) > 1e-6 or sub.currency != user.base_currency:
        base_str = f"（≈ {in_base:.2f} {user.base_currency}）"

    if days_left < 0:
        when = f"⚠️ *已逾期 {-days_left} 天*"
        head = f"🔔 *续费提醒*｜已逾期 {-days_left} 天"
    elif days_left == 0:
        when = "⚠️ *今天到期*"
        head = "🔔 *续费提醒*｜今天就到期啦"
    else:
        when = f"还有 *{days_left}* 天"
        head = f"🔔 *续费提醒*｜还有 {days_left} 天到期"

    # 关联信息
    cat = db.get(Category, sub.category_id) if sub.category_id else None
    pm = db.get(PaymentMethod, sub.payment_method_id) if sub.payment_method_id else None
    unit = _CYCLE_CN.get(sub.cycle, sub.cycle)
    cycle_str = f"每 {sub.cycle_count} {unit}" if (sub.cycle_count or 1) > 1 else f"每{unit}"

    lines = [head, ""]
    title = _escape_md(sub.name)
    if sub.plan:
        title += f"（{_escape_md(sub.plan)}）"
    lines.append(f"📦 项目：*{title}*")
    if cat:
        lines.append(f"🗂️ 分类：{_escape_md(cat.name)}")
    lines.append(f"📅 到期：*{sub.next_renewal_date}*（{when}）")
    if reminder_label:
        lines.append(f"⏰ 规则：{reminder_label}")
    lines.append(f"💰 金额：*{amount}*{base_str} · {cycle_str}")
    if pm:
        lines.append(f"💳 付款：{_escape_md(pm.name)}")
    lines.append(f"🔁 自动续费：{'开' if sub.auto_renew else '关'}")
    if sub.family_members:
        lines.append(f"👨‍👩‍👧 家庭成员：{_escape_md('、'.join(sub.family_members))}")
    if sub.remark:
        lines.append(f"📝 备注：{_escape_md(sub.remark)}")
    if sub.url:
        lines.append(f"🔗 官网：{sub.url}")

    lines.append("")
    if days_left < 0:
        lines.append("👉 该项目仍未续费，请尽快处理，恢复服务或避免账号失效。")
    elif days_left == 0:
        lines.append("👉 别忘了今天处理一下，保号 / 续费就万无一失～")
    else:
        lines.append("👉 早点安排续费，省心又安心，避免到期失效～")
    return "\n".join(lines)


def start_scheduler() -> None:
    global _scheduler, _reminder_scan_time
    if _scheduler is not None:
        return
    _reminder_scan_time = _load_reminder_scan_time()
    hour, minute = (int(x) for x in _reminder_scan_time.split(":"))

    # 启动恢复仅补齐昨天及更早的遗漏，保留今天的账期给每日任务先提醒后顺延。
    try:
        run_auto_renewals(today=date.today() - timedelta(days=1))
    except Exception as e:  # noqa: BLE001
        print(f"[scheduler] 自动续费补偿扫描失败：{type(e).__name__}: {e}")

    _scheduler = BackgroundScheduler(timezone=settings.tz)
    _scheduler.add_job(
        run_due_tasks,
        CronTrigger(hour=hour, minute=minute),
        id="daily_due_tasks",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # 小时规则在每小时的同一分钟扫描；每日主任务所在小时由 run_due_tasks 串行处理。
    _scheduler.add_job(
        run_hourly_reminder_scan,
        CronTrigger(minute=minute),
        id="hourly_reminder_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # 每天凌晨 4 点刷新汇率
    _scheduler.add_job(
        _refresh_rates_job,
        CronTrigger(hour=4, minute=0),
        id="daily_rate_refresh",
        replace_existing=True,
    )
    # 每天凌晨 3:30 自动整站备份到本地磁盘
    _scheduler.add_job(
        _auto_backup_job,
        CronTrigger(hour=3, minute=30),
        id="daily_auto_backup",
        replace_existing=True,
    )
    # 每天 08:00 检查是否到用户设定的每周汇总日
    _scheduler.add_job(
        run_weekly_digest,
        CronTrigger(hour=8, minute=0),
        id="weekly_digest",
        replace_existing=True,
    )
    _scheduler.start()


def _auto_backup_job() -> None:
    from app.services import autobackup  # 延迟导入避免循环依赖
    try:
        autobackup.run_auto_backup()
    except Exception:  # noqa: BLE001
        pass


def _refresh_rates_job() -> None:
    if database.SessionLocal is None:
        return
    db = database.SessionLocal()
    try:
        exchange.refresh_rates(db)
    except Exception:  # noqa: BLE001
        pass
    finally:
        db.close()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
