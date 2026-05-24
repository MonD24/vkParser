"""
bot_engine.py — основная логика: поиск конкурсов, выполнение условий,
                проверка победителей, очистка
"""
import json
import os
from datetime import datetime

from dotenv import load_dotenv

import database as db
import vk_client as vk
import tg_notifier as tg
from contest_parser import is_contest, is_blocked, parse_conditions
from logger import get_logger

load_dotenv()
log = get_logger("engine")


def _min_members() -> int:
    return int(os.getenv("MIN_GROUP_MEMBERS", "1000"))


def _check_group_size(owner_id: int) -> bool:
    """True если группа достаточно большая (или owner_id — пользователь)."""
    if owner_id >= 0:
        return True  # пост от пользователя — не проверяем
    count = vk.get_group_members_count(abs(owner_id))
    ok = count >= _min_members()
    if not ok:
        log.debug(f"Группа {owner_id} слишком маленькая ({count} < {_min_members()})")
    return ok


def _geo_filter(text: str) -> bool:
    """True если пост проходит гео-фильтр (или фильтр отключён)."""
    raw = os.getenv("GEO_FILTER", "").strip()
    if not raw:
        return True  # фильтр отключён — берём всё
    keywords = [k.strip().lower() for k in raw.split(",") if k.strip()]
    t = text.lower()
    return any(kw in t for kw in keywords)


def _search_keywords() -> list[str]:
    raw = os.getenv("CONTEST_KEYWORDS", "конкурс розыгрыш,giveaway приз")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _search_count() -> int:
    return int(os.getenv("SEARCH_COUNT", "20"))


# ─────────────────────────────────────────────────────────
#  1. ПОИСК НОВЫХ КОНКУРСОВ
# ─────────────────────────────────────────────────────────

def scan_for_contests():
    """Ищет конкурсы по ключевым словам через VK newsfeed.search."""
    keywords = _search_keywords()
    if not keywords:
        log.warning("CONTEST_KEYWORDS пуст — нечего искать")
        return

    found = 0
    seen_ids: set[str] = set()   # дедупликация в рамках одного запуска

    for query in keywords:
        posts = vk.search_posts(query, count=_search_count())
        for post in posts:
            owner_id = post.get("owner_id") or post.get("source_id")
            post_id  = post.get("id")
            if not owner_id or not post_id:
                continue

            vk_key = f"{owner_id}_{post_id}"
            if vk_key in seen_ids:
                continue
            seen_ids.add(vk_key)

            text = post.get("text", "")
            if not is_contest(text):
                continue
            if is_blocked(text):
                log.info(f"Пост {vk_key} заблокирован фильтром контента — пропускаем")
                continue
            if not _geo_filter(text):
                log.debug(f"Пост {vk_key} не прошёл гео-фильтр — пропускаем")
                continue
            if not _check_group_size(owner_id):
                continue
            cond = parse_conditions(text)
            if not cond["feasible"]:
                log.info(f"Конкурс {vk_key} невыполним — пропускаем")
                continue

            end_iso  = cond["end_date"].isoformat() if cond["end_date"] else None
            cond_str = _cond_summary(cond)
            new_id   = db.add_contest(owner_id, post_id, text, end_iso,
                                      conditions_raw=cond_str)
            if new_id:
                found += 1
                log.info(f"Новый конкурс #{new_id}: {vk_key} | {cond_str}")
                _fulfill_contest(new_id, owner_id, post_id, cond, vk_key, end_iso or "", cond_str)

    log.info(f"Сканирование завершено. Новых конкурсов: {found}")


def _cond_summary(cond: dict) -> str:
    parts = []
    if cond["need_repost"]:  parts.append("репост")
    if cond["need_like"]:    parts.append("лайк")
    if cond["need_join"]:    parts.append("подписка")
    if cond["need_comment"]: parts.append("комментарий")
    return ", ".join(parts) if parts else "—"


# ─────────────────────────────────────────────────────────
#  2. ВЫПОЛНЕНИЕ УСЛОВИЙ
# ─────────────────────────────────────────────────────────

def _fulfill_contest(contest_id: int, owner_id: int, post_id: int, cond: dict,
                     vk_key: str = "", end_iso: str = "", cond_str: str = ""):
    updates = {}
    reposted = False

    if cond["need_repost"]:
        repost_id = vk.repost(owner_id, post_id)
        if repost_id:
            updates["repost_id"] = repost_id
            db.log_action(contest_id, "repost", f"repost_id={repost_id}")
            reposted = True

    if cond["need_like"]:
        ok = vk.like_post(owner_id, post_id)
        if ok:
            updates["liked"] = 1
            db.log_action(contest_id, "like")

    if cond["need_join"]:
        groups = cond["groups_to_join"]
        if not groups and owner_id < 0:
            groups = [abs(owner_id)]
        # Резолвим slug → group_id если нужно
        resolved_groups = []
        for g in groups:
            if isinstance(g, int):
                resolved_groups.append(g)
            else:
                gid = vk.resolve_screen_name(g)
                if gid:
                    resolved_groups.append(gid)
                else:
                    log.debug(f"Не удалось разрезолвить slug: {g}")
        # Если вообще нет групп для вступления — пытаемся использовать автора поста
        if not resolved_groups and owner_id < 0:
            resolved_groups = [abs(owner_id)]
        joined = []
        for gid in resolved_groups:
            if vk.join_group(gid):
                joined.append(gid)
                db.log_action(contest_id, "join_group", str(gid))
        if joined:
            updates["joined_groups"] = json.dumps(joined)

    if cond["need_comment"]:
        ok = vk.post_comment(owner_id, post_id)
        if ok:
            updates["commented"] = 1
            db.log_action(contest_id, "comment")

    if updates:
        db.update_contest(contest_id, **updates)
        log.info(f"Конкурс #{contest_id}: условия выполнены: {updates}")

    # Уведомляем в TG если сделали хоть одно действие
    if updates and vk_key:
        with db.get_conn() as conn:
            row = conn.execute("SELECT text FROM contests WHERE id=?", (contest_id,)).fetchone()
        post_text = row["text"] if row else ""
        # список выполненных действий
        actions_done = []
        if reposted:                          actions_done.append("repost")
        if updates.get("liked"):              actions_done.append("like")
        if updates.get("joined_groups"):      actions_done.append("join")
        if updates.get("commented"):          actions_done.append("comment")
        tg.notify_participated(vk_key, cond_str, end_iso or "неизвестно", post_text, actions_done)


def fulfill_active_contests():
    """Повторная попытка выполнить условия для активных конкурсов (репосты слетают и т.д.)"""
    for row in db.get_active_contests():
        text = row["text"] or ""

        # Перепроверяем фильтры — вдруг пост попал в БД до ужесточения правил
        if is_blocked(text) or not is_contest(text):
            log.info(f"Конкурс #{row['id']} не прошёл повторную проверку фильтров — помечаем loser")
            db.update_contest(row["id"], status="loser")
            db.log_action(row["id"], "filtered_out_on_retry")
            continue

        # Проверяем, все ли нужные действия уже выполнены
        cond = parse_conditions(text)
        if not cond["feasible"]:
            continue

        already_done = True
        if cond["need_repost"]  and not row["repost_id"]:      already_done = False
        if cond["need_like"]    and not row["liked"]:           already_done = False
        if cond["need_join"]    and not row["joined_groups"]:   already_done = False
        if cond["need_comment"] and not row["commented"]:       already_done = False

        if already_done:
            log.debug(f"Конкурс #{row['id']} — все условия уже выполнены, пропускаем")
            continue

        _fulfill_contest(row["id"], row["owner_id"], row["post_id"], cond,
                         row["vk_post_id"], row["end_date"] or "", row["conditions_raw"] or "")


# ─────────────────────────────────────────────────────────
#  3. ПРОВЕРКА ПОБЕДИТЕЛЕЙ
# ─────────────────────────────────────────────────────────

def check_winners():
    """Проверяет завершённые конкурсы на наличие победы."""
    for row in db.get_contests_to_check():
        contest_id = row["id"]
        owner_id   = row["owner_id"]
        post_id    = row["post_id"]

        result = vk.check_winner(owner_id, post_id)
        log.info(f"Конкурс #{contest_id} {owner_id}_{post_id}: победа={result}")

        if result is True:
            db.update_contest(contest_id, status="winner")
            db.log_action(contest_id, "winner_detected")
            tg.notify_winner(row["text"] or "", row["vk_post_id"])
        elif result is False:
            db.update_contest(contest_id, status="loser")
            db.log_action(contest_id, "no_win")
            _cleanup_contest(row)
        # result is None → подождём ещё


# ─────────────────────────────────────────────────────────
#  4. ОЧИСТКА
# ─────────────────────────────────────────────────────────

def _cleanup_contest(row):
    contest_id = row["id"]

    # Удаляем репост
    if row["repost_id"]:
        vk.delete_repost(row["repost_id"])
        db.log_action(contest_id, "delete_repost")

    # Выходим из групп
    joined = json.loads(row["joined_groups"] or "[]")
    for gid in joined:
        vk.leave_group(gid)
        db.log_action(contest_id, "leave_group", str(gid))

    db.update_contest(contest_id, status="cleaned")
    tg.notify_cleaned(row["vk_post_id"])
    log.info(f"Конкурс #{contest_id} очищен")


def cleanup_old_contests():
    """Запускать периодически — убираем всё с истёкшим сроком и статусом loser."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contests WHERE status='loser'"
        ).fetchall()
    for row in rows:
        _cleanup_contest(row)


# ─────────────────────────────────────────────────────────
#  5. ГЛАВНАЯ ФУНКЦИЯ ЦИКЛА (вызывается по расписанию)
# ─────────────────────────────────────────────────────────

def run_cycle():
    log.info("=" * 50)
    log.info(f"Запуск цикла: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        scan_for_contests()
        fulfill_active_contests()
        check_winners()
        cleanup_old_contests()
    except Exception as e:
        log.error(f"Ошибка в цикле: {e}", exc_info=True)
    log.info("Цикл завершён")
    log.info("=" * 50)
