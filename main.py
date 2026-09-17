import asyncio
from src.core.telegram_bot import TelegramBot
from src.db.models import init_db
from config.settings import BOT_TOKEN

async def main():
    await init_db()
    bot = TelegramBot(BOT_TOKEN)
    print("Бот запущен...")
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
