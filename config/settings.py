import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "default_token_for_testing")
DB_PATH = os.getenv("DB_PATH", "./bot_data.db")
# Читаем строку из .env и превращаем в список строк (убираем пробелы)
ADMIN_TELEGRAM_ID = [id.strip() for id in os.getenv("ADMIN_TELEGRAM_ID", "").split(",") if id.strip()]
