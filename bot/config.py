import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "0").strip()

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    ADMIN_ID = 0

DB_PATH = BASE_DIR / "bot_data.db"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env файле!")

if not ADMIN_ID:
    print("Внимание: ADMIN_ID не задан или некорректен в .env файле!")
