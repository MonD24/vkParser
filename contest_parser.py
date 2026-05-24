"""
contest_parser.py — разбирает текст поста и извлекает условия конкурса
"""
import re
from datetime import datetime, timedelta
from logger import get_logger

log = get_logger("parser")

# ключевые слова для условий (включая эмодзи-варианты)
REPOST_KW   = ["репост", "repost", "поделись", "поделитесь", "расшар",
               "сделать репост", "репостни"]
LIKE_KW     = ["лайк", "like", "нравится", "понравится", "❤", "❤️", "👍",
               "поставить лайк", "поставь лайк", "поставить ❤"]
JOIN_KW     = ["подпис", "вступ", "подписчик", "join", "follow",
               "быть подписчик", "стать подписчик", "подпишись", "подпишитесь"]
COMMENT_KW  = ["коммент", "comment", "напиш", "отпиш", "оставь коммент"]
CONTEST_KW  = ["конкурс", "розыгрыш", "giveaway", "раздача", "победитель",
               "приз", "выигр", "разыгрыв"]

# ── Блок-лист — такие посты не репостим ──────────────────────────────────────
BLOCKED_KW = [
    # 18+
    "нижнее бель", "эротик", "секс-", "интим", "adult", "18+",
    "для взрослых", "lingerie",
    # политика / экстремизм
    "гитлер", "нацист", "фашист", "третий рейх", "hitler", "nazi",
    # запрещённые в РФ организации и персоны
    "навальн", "фбк", "алексей навальный", "navalny",
    "открытая россия", "мбх медиа",
    "свидетел иеговы", "jehovah",
    "таблига джамаат", "хизб ут-тахрир", "хамас", "исламское государство", "игил", "isis", "daesh",
    "правый сектор", " азов ", "с14",
    # лгбт — признано «пропагандой» и запрещено
    "лгбт", "лгбтq", "lgbt", "lgbtq",
    "гей-парад", "прайд", "pride parade",
    "смена пола", "трансгендер", "transgender",
    # казино / ставки
    "казино", "ставки на спорт", "букмекер", "1xbet", "1хбет",
    "melbet", "mostbet", "онлайн-казино",
    # крипто-скам
    "биткоин", "криптовалют", "nft ", "пассивный доход",
    "вложи и получи", "заработай из дома",
    # сомнительная медицина
    "похудей за", "средство для похудения", "бад ",
    # денежные призы (на карту/телефон) — не интересуют
    "на карту", "на счёт", "на счет", "перевод на карту",
    "на баланс телефона", "на номер телефона", "пополним телефон",
    "денежный приз", "денежное вознаграждение",
    "рублей на карт", "рублей победител", "рублей на счёт", "рублей на счет",
    "₽ на карт", "₽ победител", "₽ на счёт", "₽ на счет",
    "переведём деньги", "переведем деньги", "выплатим деньги",
    # маркетинг / пиар — не конкурс
    "взаимный пиар", "взаимопиар", "пиар вк", "обменяемся ссылками", "обменяться ссылк",
    "таргетолог", "продвижени", "сотрудничеств", "реклам", "smm",
    "бизнес ланч", "бизнесланч",
    # статьи и советы о маркетинге/smm — упоминают конкурсы, но не проводят их
    "совет от ", "предложение сотрудничества", "пример конкурса", "пример интерактива",
    "группу под ключ", "оформление группы", "раскрутк", "webpatriot", "fuguagency",
    "#взаимопиар", "#раскрутк", "#сетевоймаркетинг", "#пиаригры", "#маркетинговыйход",
    # итоги конкурса — уже закончился
    "итоги розыгрыша", "итоги конкурса", "победитель определён",
    "достаётся ", "поздравляем победител", "результаты розыгрыша",
    # спам-агрегаторы конкурсов
    "халявный пингвин", "halyava_pinguin", "конкурс прямо сейчас",
    "халява розыгрыш", "конкурс репост итоги",
    # сложные механики — бот/рассылка/стороннее приложение
    "activebot", "подписаться на рассылку", "подписка на рассылку",
    "напишите слово", "напиши слово", "бот в ответном",
    "сервис конкурс", "vk.cc/",
    # юридические / финансовые услуги — не конкурс товаров
    "банкротств", "юридическ", "списание долг", "конкурзилла",
    "кредитор", "арбитражн", "исполнительн производств",
]

# паттерны дат
DATE_PATTERNS = [
    (r"до\s+(\d{1,2})\s+(янв|фев|мар|апр|май|мая|июн|июл|авг|сен|окт|ноя|дек)\w*"
     r"(?:\s+(\d{4}))?", "text_date"),
    (r"до\s+(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{4}))?", "num_date"),
    (r"через\s+(\d+)\s+дн", "relative"),
    (r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{4}))?\s*(?:в\s*\d{1,2}[:\.]\d{2})?", "bare_date"),
]

MONTH_MAP = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4,
    "май": 5, "мая": 5, "июн": 6, "июл": 7,
    "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12
}


def _parse_date(text: str) -> datetime | None:
    text_l = text.lower()
    now = datetime.now()
    for pattern, kind in DATE_PATTERNS:
        m = re.search(pattern, text_l)
        if not m:
            continue
        try:
            if kind == "text_date":
                day = int(m.group(1))
                month = MONTH_MAP.get(m.group(2)[:3], now.month)
                year = int(m.group(3)) if m.group(3) else now.year
                dt = datetime(year, month, day, 23, 59)
                if dt > now:
                    return dt
            elif kind == "num_date":
                day = int(m.group(1))
                month = int(m.group(2))
                year = int(m.group(3)) if m.group(3) else now.year
                dt = datetime(year, month, day, 23, 59)
                if dt > now:
                    return dt
            elif kind == "relative":
                days = int(m.group(1))
                return now + timedelta(days=days)
            elif kind == "bare_date":
                day = int(m.group(1))
                month = int(m.group(2))
                year = int(m.group(3)) if m.group(3) else now.year
                dt = datetime(year, month, day, 23, 59)
                # bare_date берём только если явно в будущем
                if dt > now:
                    return dt
        except (ValueError, TypeError):
            continue
    return now + timedelta(days=14)  # фолбек: +14 дней


def _check_numbered_list(text: str) -> dict:
    """
    Ищет нумерованные пункты условий вида:
    1. / 1️⃣ / ✅ / • / - + текст условия
    """
    found = {"repost": False, "like": False, "join": False, "comment": False}
    # Разбиваем на строки и ищем пункты
    for line in text.split("\n"):
        line_l = line.lower()
        # убираем маркеры списка: цифры, эмодзи-цифры, ✅, •, -
        clean = re.sub(r"^[\s\-•✅☑️✔️]*[0-9️⃣1️⃣2️⃣3️⃣4️⃣5️⃣]*[\.\)]\s*", "", line_l).strip()
        if any(kw in clean for kw in REPOST_KW):
            found["repost"] = True
        if any(kw in clean for kw in LIKE_KW):
            found["like"] = True
        if any(kw in clean for kw in JOIN_KW):
            found["join"] = True
        if any(kw in clean for kw in COMMENT_KW):
            found["comment"] = True
    return found


def is_contest(text: str) -> bool:
    """
    Проверка: текст похож на активный конкурс для участия.
    Требует минимум 2 конкурсных слова + условие участия.
    Отсекает посты с итогами и спам-агрегаторы.
    """
    t = text.lower()

    # Пост объявляет итоги — уже не участвуем
    RESULTS_KW = ["итоги розыгрыша", "итоги конкурса", "победитель определён",
                  "достаётся ", "поздравляем победител", "результаты розыгрыша",
                  "достался "]
    if any(kw in t for kw in RESULTS_KW):
        return False

    # Спам-агрегатор: слишком много хэштегов и мало реального текста
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    total_lines = len(lines) or 1
    hashtag_lines = sum(1 for l in lines if l.startswith("#") or l.count("#") >= 3)
    if hashtag_lines / total_lines > 0.4:
        log.debug("Пост отклонён: слишком много хэштегов (спам-агрегатор)")
        return False

    # Слишком короткий текст — только теги без реального конкурса
    real_text = re.sub(r"#\S+", "", text).strip()
    if len(real_text) < 80:
        log.debug("Пост отклонён: слишком мало реального текста")
        return False

    # Статья/совет — конкурсы упомянуты как пример, а не проводятся
    ADVICE_KW = ["совет от ", "👂 совет", "пример конкурса", "пример интерактива",
                 "как провести конкурс", "зачем нужен конкурс",
                 "интерактивы и конкурсы", "интерактивы, конкурсы",
                 "конкурсы и giveaway", "конкурсы, giveaway",
                 "предложение сотрудничества", "webpatriot",
                 "группу под ключ", "сделаю оформление"]
    if any(kw in t for kw in ADVICE_KW):
        log.debug("Пост отклонён: статья/совет о конкурсах, не реальный конкурс")
        return False

    # Денежный приз (рубли/₽) без упоминания стима — не интересует
    STEAM_KW = ["steam", "стим", "ключ", "игр", "gift card", "подарочн"]
    has_steam = any(kw in t for kw in STEAM_KW)
    if not has_steam:
        if re.search(r"\d[\d\s.,]*(?:рублей|рубл|руб\.?|₽)", t):
            log.debug("Пост отклонён: денежный приз без стима")
            return False

    hits = sum(1 for kw in CONTEST_KW if kw in t)
    if hits < 2:
        return False

    # должно быть хотя бы одно условие участия
    all_condition_kw = REPOST_KW + LIKE_KW + JOIN_KW + COMMENT_KW
    return any(kw in t for kw in all_condition_kw)


def is_blocked(text: str) -> bool:
    """True если пост содержит нежелательный контент."""
    t = text.lower()
    for kw in BLOCKED_KW:
        if kw in t:
            log.debug(f"Пост заблокирован по слову: '{kw}'")
            return True
    return False


def parse_conditions(text: str) -> dict:
    t = text.lower()

    # Сначала ищем по всему тексту
    need_repost  = any(kw in t for kw in REPOST_KW)
    need_like    = any(kw in t for kw in LIKE_KW)
    need_join    = any(kw in t for kw in JOIN_KW)
    need_comment = any(kw in t for kw in COMMENT_KW)

    # Дополнительно парсим нумерованные списки (более точно)
    numbered = _check_numbered_list(text)
    need_repost  = need_repost  or numbered["repost"]
    need_like    = need_like    or numbered["like"]
    need_join    = need_join    or numbered["join"]
    need_comment = need_comment or numbered["comment"]

    end_date = _parse_date(text)

    # Извлекаем group_id из ссылок
    groups_to_join: list[int] = []
    for m in re.finditer(r"vk\.com/(?:club|public)(\d+)", text, re.IGNORECASE):
        groups_to_join.append(int(m.group(1)))

    HARD_KW = ["купи", "оплат", "фото", "видео", "скриншот", "selfi", "селфи",
               "тег друга", "отметь друга", "отметить друз", "отметить в комментари",
               "репост в истори", "репостить в истори",  # история — не стена
               "напишите слово", "напиши слово",          # бот-механика
               "кодовое слово", "слово-пароль", "пароль «",  # кодовые слова
               # подписка на личную страницу (не группу) — нельзя автоматизировать
               "подписка на мою страниц", "подписка на страниц", "подпишитесь на мою страниц",
               "подпишись на мою страниц", "на мою страницу",
               # конкретная фраза в кавычках (все варианты кавычек)
               "комментарий «", "комментарий \"", "комментарий \u201c", "комментарий \u2018",
               "напиши «", "напиши \"", "напиши \u201c",
               "написать «", "написать \"",
               "слово «", "слово \"",
               ]
    hard = any(kw in t for kw in HARD_KW)

    # Дополнительно: regex для «конкретная фраза» после команды написать
    # Ловим все варианты открывающих кавычек: «  "  "  '
    if not hard:
        if re.search(u"(напиш|коммент|написать|write)[^\u00ab\u00bb\u201c\u2018\n]{0,30}[\u00ab\u201c\u2018\"]", t):
            hard = True

    # Если нужна подписка на группу, но в тексте нет ссылки на группу —
    # группа указана по названию (не по ссылке), автоматически вступить невозможно
    if need_join and not groups_to_join:
        # Проверяем: пост сам из группы (owner_id < 0) — тогда ОК, подпишемся на неё
        # Это решается в bot_engine.py, здесь просто помечаем как требующий ссылки
        # Если в тексте есть "подписка на группу" или "вступите в группу" без ссылки — hard
        if re.search(r"подписк[ауи] на группу|вступ[ие]те? в группу|подпишитесь на группу", t):
            log.debug("Пост отклонён: требует подписки на группу без ссылки")
            hard = True

    # выполнимо если есть хотя бы одно автоматизируемое условие (включая комментарий)
    feasible = (need_repost or need_like or need_join or need_comment) and not hard

    log.debug(
        f"Условия: repost={need_repost} like={need_like} join={need_join} "
        f"comment={need_comment} feasible={feasible} end={end_date}"
    )

    if not feasible and not hard:
        log.debug(f"Текст поста (первые 200 символов): {text[:200].strip()!r}")

    return {
        "need_repost":    need_repost,
        "need_like":      need_like,
        "need_join":      need_join,
        "need_comment":   need_comment,
        "end_date":       end_date,
        "feasible":       feasible,
        "groups_to_join": groups_to_join,
    }
