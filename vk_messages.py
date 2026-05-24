"""
vk_messages.py — поллинг VK личных сообщений и форвард в Telegram
Запускается в отдельном потоке из main.py
"""
import time
import os
import threading
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.exceptions import ApiError
from dotenv import load_dotenv
from logger import get_logger
import tg_notifier as tg

load_dotenv()
log = get_logger("vk_msg")

_stop_event = threading.Event()


def _get_session():
    token = os.getenv("VK_TOKEN")
    session = vk_api.VkApi(token=token, api_version="5.131")
    return session


def _sender_name(vk_api_obj, user_id: int) -> str:
    try:
        r = vk_api_obj.users.get(user_ids=user_id, fields="first_name,last_name")
        u = r[0]
        return f"{u['first_name']} {u['last_name']}"
    except Exception:
        return f"id{user_id}"


def _poll_messages_once(vk, last_msg_id: int) -> int:
    """Проверяем новые входящие сообщения через messages.getDialogs / messages.get."""
    try:
        res = vk.messages.getConversations(count=20, filter="unread")
        items = res.get("items", [])
        new_last = last_msg_id
        for item in items:
            msg = item.get("last_message", {})
            msg_id = msg.get("id", 0)
            if msg_id <= last_msg_id:
                continue
            # только входящие (from_id != наш id)
            from_id = msg.get("from_id", 0)
            my_id = int(os.getenv("VK_USER_ID", 0))
            if from_id == my_id:
                continue
            text = msg.get("text", "")
            sender = _sender_name(vk, from_id)
            vk_link = f"https://vk.com/im?sel={from_id}"
            notify_msg = (
                f"📩 <b>Новое сообщение ВКонтакте</b>\n"
                f"👤 <a href=\"{vk_link}\">{sender}</a>\n"
                f"💬 {text[:500]}"
            )
            tg.notify(notify_msg)
            log.info(f"Переслано сообщение от {sender}: {text[:80]}")
            new_last = max(new_last, msg_id)
        return new_last
    except ApiError as e:
        log.warning(f"messages.getConversations: {e}")
        return last_msg_id


def forward_messages():
    """Основной цикл поллинга через polling (не LongPoll — нет pts у user token)."""
    log.info("VK→TG форвард сообщений запущен (режим polling каждые 30с)")
    last_msg_id = 0
    # Получаем текущий последний id чтобы не пересылать старые
    try:
        session = _get_session()
        vk = session.get_api()
        res = vk.messages.getConversations(count=1)
        items = res.get("items", [])
        if items:
            last_msg_id = items[0].get("last_message", {}).get("id", 0)
        log.info(f"Стартовый last_msg_id={last_msg_id}")
    except Exception as e:
        log.warning(f"Не удалось получить last_msg_id: {e}")

    while not _stop_event.is_set():
        try:
            session = _get_session()
            vk = session.get_api()
            last_msg_id = _poll_messages_once(vk, last_msg_id)
        except Exception as e:
            log.warning(f"Ошибка поллинга сообщений: {e}")
        _stop_event.wait(30)  # проверяем каждые 30 секунд

    log.info("VK→TG форвард сообщений остановлен")


def start_in_thread() -> threading.Thread:
    t = threading.Thread(target=forward_messages, daemon=True, name="vk-messages")
    t.start()
    return t


def stop():
    _stop_event.set()
