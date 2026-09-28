import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "default_token_for_testing")
DB_PATH = os.getenv("DB_PATH", "./bot_data.db")
# Идентификаторы суперадминов (список через запятую)
ADMIN_USER_IDS = [uid.strip() for uid in os.getenv("ADMIN_USER_IDS", "").split(",") if uid.strip()]
# Обратная совместимость со старыми конфигами на базе Telegram
if not ADMIN_USER_IDS:
    ADMIN_USER_IDS = [uid.strip() for uid in os.getenv("ADMIN_TELEGRAM_ID", "").split(",") if uid.strip()]
