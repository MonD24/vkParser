"""
tg_control.py — Telegram-бот для управления: /start /stop /status /now
Запускается в отдельном потоке из main.py
"""
import os
import threading
from dotenv import load_dotenv
from logger import get_logger

load_dotenv()
log = get_logger("tg_control")

# Импортируем здесь чтобы не ломать tg_notifier если telegram не установлен
try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
    _TG_AVAILABLE = True
except ImportError:
    _TG_AVAILABLE = False

# Глобальные ссылки — устанавливаются из main.py
_scheduler_ref = None
_run_cycle_fn  = None
_bot_running   = True
_cycle_lock    = threading.Lock()  # защита от параллельных /now


def set_refs(scheduler, run_cycle_fn):
    global _scheduler_ref, _run_cycle_fn
    _scheduler_ref = scheduler
    _run_cycle_fn  = run_cycle_fn


def _is_owner(update: "Update") -> bool:
    """Принимаем команды только от владельца (TG_CHAT_ID)."""
    owner = str(os.getenv("TG_CHAT_ID", ""))
    return str(update.effective_chat.id) == owner


async def cmd_start(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE"):
    if not _is_owner(update): return
    global _bot_running
    if _scheduler_ref and not _scheduler_ref.running:
        _scheduler_ref.resume()
        _bot_running = True
        await update.message.reply_text("▶️ Бот возобновлён. Циклы по расписанию активны.")
        log.info("Бот возобновлён по команде /start")
    else:
        await update.message.reply_text("✅ Бот уже работает.")


async def cmd_stop(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE"):
    if not _is_owner(update): return
    global _bot_running
    if _scheduler_ref and _scheduler_ref.running:
        _scheduler_ref.pause()
        _bot_running = False
        await update.message.reply_text("⏸ Бот приостановлен. Расписание заморожено.\nОтправь /start чтобы возобновить.")
        log.info("Бот приостановлен по команде /stop")
    else:
        await update.message.reply_text("⏸ Бот уже остановлен.")


async def cmd_now(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE"):
    if not _is_owner(update): return
    if not _cycle_lock.acquire(blocking=False):
        await update.message.reply_text("⏳ Цикл уже выполняется, подождите...")
        return
    try:
        await update.message.reply_text("🔍 Запускаю внеплановый цикл поиска...")
        log.info("Внеплановый цикл по команде /now")
        if _run_cycle_fn:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _run_cycle_fn)
        await update.message.reply_text("✅ Цикл завершён.")
    finally:
        _cycle_lock.release()


async def cmd_status(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE"):
    if not _is_owner(update): return
    import database as db
    active = db.get_active_contests()
    status = "▶️ работает" if _bot_running else "⏸ пауза"
    jobs = []
    if _scheduler_ref:
        for job in _scheduler_ref.get_jobs():
            nxt = job.next_run_time
            jobs.append(f"  • {job.name}: {nxt.strftime('%H:%M МСК') if nxt else 'заморожен'}")
    jobs_str = "\n".join(jobs) if jobs else "  нет"
    msg = (
        f"🤖 <b>Статус бота</b>\n"
        f"Состояние: {status}\n"
        f"Активных конкурсов: {len(active)}\n\n"
        f"📅 Расписание:\n{jobs_str}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_list(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE"):
    if not _is_owner(update): return
    import database as db
    rows = db.get_active_contests()
    if not rows:
        await update.message.reply_text("📭 Активных конкурсов нет.")
        return
    lines = ["📋 <b>Активные конкурсы:</b>"]
    for r in rows:
        link = f"https://vk.com/wall{r['vk_post_id']}"
        end = (r["end_date"] or "?")[:16]
        lines.append(f"• <a href=\"{link}\">{r['vk_post_id']}</a> — до {end}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


def run_control_bot():
    """Запускает TG control bot. Должен вызываться из ГЛАВНОГО потока."""
    if not _TG_AVAILABLE:
        log.warning("python-telegram-bot не установлен — управляющий бот недоступен")
        return
    token = os.getenv("TG_BOT_TOKEN", "")
    if not token or token == "your_telegram_bot_token":
        log.warning("TG_BOT_TOKEN не задан — управляющий бот недоступен")
        return
    try:
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CommandHandler("start",  cmd_start))
        app.add_handler(CommandHandler("stop",   cmd_stop))
        app.add_handler(CommandHandler("now",    cmd_now))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("list",   cmd_list))
        log.info("TG управляющий бот запущен. Команды: /start /stop /now /status /list")
        # run_polling работает только из главного потока — именно там и вызываемся
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        log.error(f"TG control bot ошибка: {e}")


def start_in_thread() -> threading.Thread:
    t = threading.Thread(target=run_control_bot, daemon=True, name="tg-control")
    t.start()
    return t
