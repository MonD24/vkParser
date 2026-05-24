"""
vk_client.py — обёртка над VK API
"""
import time
import random
import json
import os
import vk_api
from vk_api.exceptions import ApiError
from dotenv import load_dotenv
from logger import get_logger

load_dotenv()
log = get_logger("vk_client")

_vk_session = None
_vk = None


def _get_vk():
    global _vk_session, _vk
    if _vk is None:
        token = os.getenv("VK_TOKEN")
        if not token or token == "your_vk_user_token_here":
            raise RuntimeError("VK_TOKEN не задан в .env!")
        _vk_session = vk_api.VkApi(token=token)
        _vk = _vk_session.get_api()
        log.info("VK API авторизован")
    return _vk


def _delay():
    lo = int(os.getenv("ACTION_DELAY_MIN", 5))
    hi = int(os.getenv("ACTION_DELAY_MAX", 15))
    t = random.uniform(lo, hi)
    log.debug(f"Пауза {t:.1f}с")
    time.sleep(t)


# ---------- публичные функции ----------

def get_wall_posts(owner_id: int, count: int = 20) -> list[dict]:
    """Получить последние посты со стены группы."""
    vk = _get_vk()
    try:
        res = vk.wall.get(owner_id=owner_id, count=count, filter="owner")
        return res.get("items", [])
    except ApiError as e:
        log.warning(f"wall.get owner={owner_id}: {e}")
        return []


def repost(owner_id: int, post_id: int) -> int | None:
    """Репостит запись на свою стену. Возвращает post_id репоста."""
    vk = _get_vk()
    obj = f"wall{owner_id}_{post_id}"
    try:
        res = vk.wall.repost(object=obj)
        _delay()
        repost_id = res.get("post_id")
        log.info(f"Репост {obj} → post_id={repost_id}")
        return repost_id
    except ApiError as e:
        log.error(f"Ошибка репоста {obj}: {e}")
        return None


def delete_repost(repost_post_id: int) -> bool:
    """Удаляет наш репост со своей стены."""
    vk = _get_vk()
    user_id = int(os.getenv("VK_USER_ID", 0))
    try:
        vk.wall.delete(owner_id=user_id, post_id=repost_post_id)
        _delay()
        log.info(f"Репост {repost_post_id} удалён")
        return True
    except ApiError as e:
        log.error(f"Ошибка удаления репоста {repost_post_id}: {e}")
        return False


def like_post(owner_id: int, post_id: int) -> bool:
    vk = _get_vk()
    try:
        vk.likes.add(type="post", owner_id=owner_id, item_id=post_id)
        _delay()
        log.info(f"Лайк {owner_id}_{post_id}")
        return True
    except ApiError as e:
        log.warning(f"Лайк {owner_id}_{post_id}: {e}")
        return False


def join_group(group_id: int) -> bool:
    """Вступить в группу (group_id без минуса)."""
    vk = _get_vk()
    try:
        vk.groups.join(group_id=group_id)
        _delay()
        log.info(f"Вступили в группу {group_id}")
        return True
    except ApiError as e:
        log.warning(f"Вступление в группу {group_id}: {e}")
        return False


def leave_group(group_id: int) -> bool:
    """Покинуть группу."""
    vk = _get_vk()
    try:
        vk.groups.leave(group_id=group_id)
        _delay()
        log.info(f"Вышли из группы {group_id}")
        return True
    except ApiError as e:
        log.warning(f"Выход из группы {group_id}: {e}")
        return False


def search_posts(query: str, count: int = 20) -> list[dict]:
    """Поиск постов по всему VK через newsfeed.search."""
    vk = _get_vk()
    try:
        res = vk.newsfeed.search(q=query, count=count, extended=0)
        items = res.get("items", [])
        # гарантируем наличие owner_id (иногда приходит как source_id)
        for item in items:
            if "owner_id" not in item and "source_id" in item:
                item["owner_id"] = item["source_id"]
        log.info(f"newsfeed.search '{query}': найдено {len(items)} постов")
        return items
    except ApiError as e:
        log.warning(f"newsfeed.search '{query}': {e}")
        return []


def post_comment(owner_id: int, post_id: int) -> bool:
    """Оставляет случайный комментарий под постом."""
    import random
    COMMENTS = [
        "Участвую! 🔥",
        "Хочу выиграть! 🎉",
        "Отличный конкурс! Участвую 👍",
        "Удачи всем участникам! Я в деле 🙌",
        "Классный приз, участвую! ✨",
        "Участвую с удовольствием! 🎁",
        "Мне нравится! Участвую 🤞",
    ]
    vk = _get_vk()
    text = random.choice(COMMENTS)
    try:
        vk.wall.addComment(owner_id=owner_id, post_id=post_id, message=text)
        _delay()
        log.info(f"Комментарий под {owner_id}_{post_id}: «{text}»")
        return True
    except ApiError as e:
        log.warning(f"Комментарий {owner_id}_{post_id}: {e}")
        return False


def get_my_wall_posts(count: int = 10) -> list[dict]:
    """Получить свои последние посты (для поиска репостов)."""
    vk = _get_vk()
    user_id = int(os.getenv("VK_USER_ID", 0))
    try:
        res = vk.wall.get(owner_id=user_id, count=count)
        return res.get("items", [])
    except ApiError as e:
        log.warning(f"get_my_wall: {e}")
        return []


def get_group_members_count(group_id: int) -> int:
    """Возвращает кол-во участников группы. group_id — без минуса."""
    vk = _get_vk()
    try:
        res = vk.groups.getById(group_id=group_id, fields="members_count")
        return res[0].get("members_count", 0)
    except ApiError as e:
        log.warning(f"groups.getById {group_id}: {e}")
        return 0


def check_winner(owner_id: int, post_id: int) -> bool | None:
    """
    Проверка победителя — смотрим свежие посты группы после даты конкурса.
    Ищем упоминание нашего user_id в тексте поста или в комментариях к нему.
    Возвращает True (победа) / False (не нашли) / None (посты недоступны).
    """
    vk = _get_vk()
    user_id = str(os.getenv("VK_USER_ID", ""))

    # 1. Смотрим последние 20 постов группы — ищем пост с итогами
    try:
        posts = vk.wall.get(owner_id=owner_id, count=20, filter="owner").get("items", [])
    except ApiError:
        return None

    WINNER_KW = ["победитель", "победил", "итог", "результат", "выигр",
                 "поздравля", "congratul", "winner"]

    for p in posts:
        # пропускаем сам конкурсный пост
        if p["id"] == post_id:
            continue
        txt = p.get("text", "").lower()

        # пост выглядит как объявление итогов?
        is_results_post = any(kw in txt for kw in WINNER_KW)
        if not is_results_post:
            continue

        # наш id упомянут в тексте?
        if user_id and user_id in txt:
            log.info(f"Победа! Упоминание {user_id} в посте {owner_id}_{p['id']}")
            return True

        # ищем в комментариях к посту-итогов
        try:
            comments = vk.wall.getComments(
                owner_id=owner_id, post_id=p["id"],
                count=100, sort="desc"
            ).get("items", [])
            for c in comments:
                ctxt = c.get("text", "").lower()
                if user_id and user_id in ctxt:
                    log.info(f"Победа! Упоминание {user_id} в комментарии поста {owner_id}_{p['id']}")
                    return True
        except ApiError:
            pass

    return False
