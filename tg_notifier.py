"""
tg_notifier.py — отправка уведомлений в Telegram
"""
import os
import asyncio
import telegram
from dotenv import load_dotenv
from logger import get_logger

load_dotenv()
log = get_logger("tg_notifier")


async def _send(text: str):
    token   = os.getenv("TG_BOT_TOKEN", "")
    chat_id = os.getenv("TG_CHAT_ID", "")
    if not token or not chat_id or token == "your_telegram_bot_token":
        log.warning("TG_BOT_TOKEN или TG_CHAT_ID не заданы — уведомление пропущено")
        return
    bot = telegram.Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    log.info(f"TG уведомление отправлено: {text[:80]}")


def notify(text: str):
    """Синхронная обёртка."""
    try:
        asyncio.run(_send(text))
    except Exception as e:
        log.error(f"TG ошибка: {e}")


def notify_winner(contest_text: str, vk_post_id: str):
    link = _post_link(vk_post_id)
    msg = (
        "🏆 <b>ПОБЕДА!</b>\n\n"
        f"🔗 <a href=\"{link}\">{vk_post_id}</a>\n\n"
        f"{contest_text[:300]}..."
    )
    notify(msg)


def _extract_prize(text: str) -> str:
    """Пытается вытащить из текста что разыгрывается."""
    import re
    # Ищем строку после слов: приз, разыгрываем, выиграй, получи
    patterns = [
        r"разыгрыва[^\n:—–]{0,5}[:\s—–]+([^\n]{5,80})",
        r"приз[^\n:—–]{0,5}[:\s—–]+([^\n]{5,80})",
        r"выиграй\s+([^\n]{5,60})",
        r"получи[^\n]{0,5}\s+([^\n]{5,60})",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:100]
    return "не определено"


def _post_link(vk_post_id: str) -> str:
    """Конвертирует 'owner_post' или '-123_456' в ссылку vk.com/wall."""
    key = vk_post_id.replace("_", "_")  # уже правильный формат
    # убираем возможный пробел, нормализуем
    key = key.strip().replace(" ", "_")
    return f"https://vk.com/wall{key}"


def notify_participated(vk_post_id: str, conditions: str, end_date: str,
                        post_text: str = "", actions_done: list = None):
    """Уведомление об участии — отправляется при любом выполненном действии."""
    prize = _extract_prize(post_text) if post_text else "не определено"
    link = _post_link(vk_post_id)
    end_pretty = end_date[:16] if len(end_date) >= 16 else end_date

    # Иконки выполненных действий
    icons = []
    done = actions_done or []
    if "repost"  in done: icons.append("🔁 репост")
    if "like"    in done: icons.append("❤️ лайк")
    if "join"    in done: icons.append("👥 подписка")
    if "comment" in done: icons.append("💬 комментарий")
    actions_str = ", ".join(icons) if icons else conditions

    msg = (
        f"✅ <b>Участвую в конкурсе</b>\n"
        f"🔗 <a href=\"{link}\">{vk_post_id}</a>\n"
        f"🎁 Приз: {prize}\n"
        f"🎯 Сделано: {actions_str}\n"
        f"📅 До: {end_pretty}"
    )
    notify(msg)


# Обратная совместимость
def notify_reposted(vk_post_id: str, conditions: str, end_date: str, post_text: str = ""):
    notify_participated(vk_post_id, conditions, end_date, post_text, ["repost"])


def notify_start(count: int):
    # Тихий старт — не пишем в TG
    pass


def notify_new_contest(vk_post_id: str, end_date: str, conditions: str):
    # Не пишем — напишем только когда реально репостнём
    pass


def notify_cleaned(vk_post_id: str):
    # Тихая очистка — не пишем
    pass
