import asyncio
import logging
from src.core.max_bot import MaxBot
from src.db.models import init_db
from config.settings import BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

async def main():
    await init_db()
    bot = MaxBot(BOT_TOKEN)
    logging.getLogger(__name__).info("Бот для мессенджера MAX запущен...")
    try:
        await bot.run()
    except KeyboardInterrupt:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
