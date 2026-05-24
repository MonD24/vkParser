"""
fill_profile.py — одноразовый скрипт для полного заполнения профиля ВКонтакте.

ЗАЧЕМ:
  Бот участвует в конкурсах от лица реального пользователя.
  Пустой профиль выглядит подозрительно и может быть забанен.
  Этот скрипт заполняет профиль «как у живого человека»:
  аватар, анкета, посты на стене — всё сразу, за один запуск.

КАК ИСПОЛЬЗОВАТЬ:
  1. Отредактируй константы в разделе "ДАННЫЕ ПРОФИЛЯ" ниже
     (имя, город, интересы, посты — всё под себя)
  2. Запусти: .venv/Scripts/python.exe fill_profile.py
  3. Подтверди запуск нажав 'y'
  4. Скрипт заполнит всё и покажет итоговый профиль

ЧТО ЗАПОЛНЯЕТСЯ:
  ✅ Имя, фамилия, дата рождения, пол, город, родной город
  ✅ Статус («подпись» под именем)
  ✅ О себе, интересы, деятельность, музыка, фильмы, книги, сериалы, цитата
  ✅ Мировоззрение: религия, политические взгляды, жизненные приоритеты
  ✅ Образование (университет + год выпуска)
  ✅ Место работы (опционально)
  ✅ Аватар — AI-сгенерированное фото с thispersondoesnotexist.com
     (каждый раз новое случайное лицо, не существующего человека)
  ✅ Несколько постов на стену (публикуются с паузами, как живой человек)

ПРИМЕЧАНИЕ:
  Скрипт одноразовый — не встроен в бота, не запускается автоматически.
  Повторный запуск перезапишет данные профиля и добавит новые посты на стену.
"""
import os
import io
import time
import random
import requests
import vk_api
from vk_api.exceptions import ApiError
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════
#  ДАННЫЕ ПРОФИЛЯ — редактируй под себя
# ══════════════════════════════════════════════════════════════════

FIRST_NAME  = "Иван"               # ← замени на своё имя
LAST_NAME   = "Иванов"             # ← замени на свою фамилию
BDATE       = "10.3.1998"          # дд.мм.гггг — дата рождения
SEX         = 2                    # 1=женский, 2=мужской
CITY_ID     = 2                    # 2=Санкт-Петербург  (1=Москва, 49=Екатеринбург и т.д.)
HOME_CITY   = "Казань"             # откуда родом (текстом)

STATUS = "Люблю игры и хорошее кино 🎬"   # ← статус профиля

ABOUT = (
    "Обычный парень, живу в Питере. "
    "Работаю в IT, в свободное время играю на PC и смотрю сериалы. "
    "Участвую в конкурсах — иногда везёт 😄"
)
INTERESTS   = "Игры, кино, технологии, музыка, путешествия"
ACTIVITIES  = "Программирование, онлайн-игры, YouTube"
MUSIC       = "Imagine Dragons, Radiohead, Земфира, IC3PEAK"
MOVIES      = "Интерстеллар, Начало, Матрица, Blade Runner 2049"
BOOKS       = "Стругацкие, Пелевин, Стивен Кинг"
QUOTES      = "«Лучше сделать и пожалеть, чем не сделать и пожалеть»"
TV          = "Breaking Bad, Чёрное зеркало, Westworld"

# Образование — ID университета можно найти через поиск в настройках VK
# Популярные: 399=МГУ, 430=СПбГУ, 380=МГТУ им.Баумана, 498=НГУ
UNIVERSITY_ID   = 430   # ← замени на свой
UNIVERSITY_NAME = "СПбГУ"
FACULTY_ID      = 0     # 0 = не указывать факультет
GRADUATION_YEAR = 2020  # ← год окончания

# Работа (оставь пустым если не нужно)
COMPANY_NAME  = ""   # например "Яндекс"
JOB_TITLE     = ""   # например "Разработчик"

# Мировоззрение
RELIGION      = ""   # например "Православие" или оставь пустым
POLITICAL     = 3    # 1=коммунист., 2=социалист., 3=умеренные, 4=либеральные,
                     # 5=консерват., 6=монархич., 7=ультраконс., 8=индифферент., 9=либертар.
LIFE_MAIN     = 2    # 1=красота/искусство, 2=саморазвитие, 3=развлечения,
                     # 4=наука, 5=деньги/власть, 6=слава, 7=семья, 8=здоровье
PEOPLE_MAIN   = 1    # 1=ум/творчество, 2=доброта/честность, 3=красота/здоровье,
                     # 4=власть/богатство, 5=смелость, 6=юмор/жизнелюбие
SMOKING       = 1    # 1=резко негат., 2=негат., 3=нейтральное, 4=компромисс, 5=нейтральное
ALCOHOL       = 2    # аналогично

# Посты на стену — будут опубликованы с паузой 8-20с между ними
# Замени на что-то своё или оставь как есть
WALL_POSTS = [
    "Наконец-то взял игру, которую откладывал полгода. Стоило того — однозначно 🔥",
    "Воскресный вечер, горячий чай и хороший сериал — идеальный отдых 🍵",
    "Питер в туман — совсем другой город. Люблю такую атмосферу 🌫️",
    "Нашёл интересный конкурс на Steam-ключ. Держите кулачки 🤞 #розыгрыш",
    "«Интерстеллар» смотрел уже раза три, и каждый раз по-новому. Нолан — гений.",
    "Пятница — лучший день недели. Чем занимаетесь в выходные?",
]

# ══════════════════════════════════════════════════════════════════


def get_vk():
    token = os.getenv("VK_TOKEN")
    if not token or token == "your_vk_user_token_here":
        raise RuntimeError("VK_TOKEN не задан в .env!")
    session = vk_api.VkApi(token=token)
    return session.get_api(), session


def _pause(lo=1.5, hi=3.0):
    time.sleep(random.uniform(lo, hi))


def fill_main_info(vk):
    print("\n📝 Основная информация...")
    try:
        vk.account.saveProfileInfo(
            first_name=FIRST_NAME,
            last_name=LAST_NAME,
            bdate=BDATE,
            bdate_visibility=2,  # 2=показывать всем
            sex=SEX,
            city_id=CITY_ID,
            home_city=HOME_CITY,
        )
        print("  ✅ Имя, дата рождения, пол, город, родной город")
    except ApiError as e:
        print(f"  ⚠️  saveProfileInfo (main): {e}")

    _pause()

    try:
        vk.status.set(text=STATUS)
        print(f"  ✅ Статус: «{STATUS}»")
    except ApiError as e:
        print(f"  ⚠️  status.set: {e}")

    _pause()

    try:
        vk.account.saveProfileInfo(
            about=ABOUT,
            interests=INTERESTS,
            activities=ACTIVITIES,
            music=MUSIC,
            movies=MOVIES,
            books=BOOKS,
            quotes=QUOTES,
            tv=TV,
        )
        print("  ✅ О себе, интересы, музыка, фильмы, книги, цитата")
    except ApiError as e:
        print(f"  ⚠️  saveProfileInfo (about): {e}")


def fill_worldview(vk):
    print("\n🧭 Мировоззрение...")
    try:
        vk.account.saveProfileInfo(
            religion=RELIGION,
            political=POLITICAL,
            life_main=LIFE_MAIN,
            people_main=PEOPLE_MAIN,
            smoking=SMOKING,
            alcohol=ALCOHOL,
        )
        print("  ✅ Религия, политические взгляды, жизненные приоритеты")
    except ApiError as e:
        print(f"  ⚠️  saveProfileInfo (worldview): {e}")


def fill_education(vk):
    print("\n🎓 Образование...")
    if not UNIVERSITY_ID:
        print("  ⏭️  Пропущено (UNIVERSITY_ID не задан)")
        return
    try:
        vk.account.saveProfileInfo(
            university=UNIVERSITY_ID,
            university_name=UNIVERSITY_NAME,
            faculty=FACULTY_ID,
            graduation=GRADUATION_YEAR,
        )
        print(f"  ✅ {UNIVERSITY_NAME}, выпуск {GRADUATION_YEAR}")
    except ApiError as e:
        print(f"  ⚠️  saveProfileInfo (education): {e}")


def fill_career(vk):
    if not COMPANY_NAME:
        return
    print("\n💼 Место работы...")
    try:
        vk.account.saveProfileInfo(
            company=COMPANY_NAME,
            job=JOB_TITLE,
        )
        print(f"  ✅ {COMPANY_NAME} — {JOB_TITLE}")
    except ApiError as e:
        print(f"  ⚠️  saveProfileInfo (career): {e}")


def upload_avatar(vk, session):
    print("\n🖼️  Аватар...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get("https://thispersondoesnotexist.com/", headers=headers, timeout=15)
        resp.raise_for_status()
        img_data = resp.content
        print(f"  ✅ Фото скачано ({len(img_data)//1024} КБ)")
    except Exception as e:
        print(f"  ❌ Не удалось скачать фото: {e}")
        return

    try:
        upload_server = vk.photos.getOwnerPhotoUploadServer()
        upload_url = upload_server["upload_url"]
        upload_resp = requests.post(
            upload_url,
            files={"photo": ("avatar.jpg", io.BytesIO(img_data), "image/jpeg")},
            timeout=30,
        )
        upload_resp.raise_for_status()
        upload_data = upload_resp.json()
        vk.photos.saveOwnerPhoto(
            server=upload_data.get("server", ""),
            hash=upload_data.get("hash", ""),
            photo=upload_data.get("photo", ""),
        )
        print("  ✅ Аватар установлен")
    except Exception as e:
        print(f"  ❌ Ошибка загрузки аватара: {e}")


def post_wall_posts(vk):
    print(f"\n📰 Публикую {len(WALL_POSTS)} постов на стену...")
    for i, text in enumerate(WALL_POSTS, 1):
        try:
            vk.wall.post(message=text, from_group=0)
            print(f"  ✅ [{i}/{len(WALL_POSTS)}] {text[:50]}...")
        except ApiError as e:
            print(f"  ⚠️  wall.post [{i}]: {e}")
        _pause(8, 20)   # пауза между постами — имитируем живого пользователя


def check_profile(vk):
    print("\n🔍 Текущий профиль:")
    try:
        info = vk.users.get(
            fields="photo_200,status,about,interests,activities,music,movies,books,"
                   "quotes,tv,bdate,city,home_city,sex,universities,occupation,personal"
        )[0]
        print(f"  Имя:        {info.get('first_name')} {info.get('last_name')} (id{info.get('id')})")
        print(f"  Пол:        {'мужской' if info.get('sex') == 2 else 'женский'}")
        print(f"  Дата рожд.: {info.get('bdate', '—')}")
        print(f"  Город:      {info.get('city', {}).get('title', '—')}")
        print(f"  Родной:     {info.get('home_city', '—')}")
        print(f"  Статус:     {info.get('status', '—')}")
        print(f"  О себе:     {(info.get('about') or '—')[:80]}")
        print(f"  Интересы:   {(info.get('interests') or '—')[:60]}")
        print(f"  Музыка:     {(info.get('music') or '—')[:60]}")
        unis = info.get("universities", [])
        if unis:
            print(f"  Учёба:      {unis[0].get('name','—')} ({unis[0].get('graduation','?')})")
        occ = info.get("occupation")
        if occ:
            print(f"  Работа:     {occ.get('name','—')} — {occ.get('type','—')}")
        personal = info.get("personal", {})
        if personal:
            print(f"  Религия:    {personal.get('religion','—')}")
        print(f"  Аватар:     {'есть ✅' if info.get('photo_200') else 'нет ❌'}")
    except ApiError as e:
        print(f"  ⚠️  users.get: {e}")


def main():
    print("=" * 55)
    print("  VK Profile Filler — полное заполнение профиля")
    print("=" * 55)

    vk, session = get_vk()
    check_profile(vk)

    print("\n" + "─" * 55)
    print("Что будет сделано:")
    print("  1. Основная анкета (имя, дата, город, статус, о себе,")
    print("     интересы, музыка, фильмы, книги, цитата)")
    print("  2. Мировоззрение (религия, политика, приоритеты)")
    print("  3. Образование")
    if COMPANY_NAME:
        print("  4. Место работы")
    print(f"  5. Аватар (AI-фото)")
    print(f"  6. {len(WALL_POSTS)} постов на стену")
    print("─" * 55)
    answer = input("Продолжить? [y/N]: ").strip().lower()
    if answer != "y":
        print("Отменено.")
        return

    fill_main_info(vk)
    fill_worldview(vk)
    fill_education(vk)
    fill_career(vk)
    upload_avatar(vk, session)
    post_wall_posts(vk)

    print("\n" + "─" * 55)
    check_profile(vk)
    print("\n✅ Профиль полностью заполнен!")


if __name__ == "__main__":
    main()
