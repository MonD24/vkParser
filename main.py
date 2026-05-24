"""
main.py — точка входа, планировщик APScheduler
"""
import sys
import io
# Фикс кодировки на Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import os
import sys
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

import database as db
import tg_notifier as tg
import tg_control
import vk_messages
from bot_engine import run_cycle
from logger import get_logger

load_dotenv()
log = get_logger("main")


def _parse_schedule() -> list[tuple[int, int]]:
    """Парсит SCHEDULE_TIMES=09:00,14:00,20:00 → [(9,0),(14,0),(20,0)]"""
    raw = os.getenv("SCHEDULE_TIMES", "09:00,14:00,20:00")
    times = []
    for t in raw.split(","):
        t = t.strip()
        try:
            h, m = map(int, t.split(":"))
            times.append((h, m))
        except ValueError:
            log.warning(f"Неверный формат времени: {t}")
    return times or [(9, 0), (14, 0), (20, 0)]


def main():
    log.info("🤖 VK Contest Bot стартует...")

    # Инициализация БД
    db.init_db()

    # Уведомление в TG о запуске
    active = db.get_active_contests()
    tg.notify_start(len(active))

    # Создаём планировщик в фоне (не блокирует главный поток)
    scheduler = BackgroundScheduler(timezone="Europe/Moscow")
    times = _parse_schedule()

    for h, m in times:
        scheduler.add_job(
            run_cycle,
            trigger=CronTrigger(hour=h, minute=m, timezone="Europe/Moscow"),
            id=f"cycle_{h:02d}{m:02d}",
            name=f"Цикл {h:02d}:{m:02d}",
            misfire_grace_time=300,
            replace_existing=True,
        )
        log.info(f"  Запланирован цикл в {h:02d}:{m:02d} МСК")

    scheduler.start()

    # Передаём ссылку на scheduler в tg_control
    tg_control.set_refs(scheduler, run_cycle)

    # Запускаем VK→TG форвард сообщений в фоне
    if os.getenv("VK_FORWARD_MESSAGES", "true").lower() == "true":
        vk_messages.start_in_thread()
        log.info("VK→TG форвард сообщений запущен в фоне")

    # Запустить немедленно при старте
    if "--now" in sys.argv:
        log.info("--now: запускаем цикл немедленно")
        run_cycle()

    log.info("Планировщик запущен. Управление через Telegram: /start /stop /now /status /list")

    try:
        # TG control bot запускаем из ГЛАВНОГО потока (требование python-telegram-bot)
        tg_control.run_control_bot()
    except (KeyboardInterrupt, SystemExit):
        log.info("Бот остановлен")
        scheduler.shutdown()
        vk_messages.stop()


if __name__ == "__main__":
    main()
