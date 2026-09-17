from sqlalchemy.future import select
from src.db.models import AsyncSessionLocal, UserDB
from src.core.base_bot import BaseBot

class NotificationService:
    def __init__(self, bot: BaseBot):
        self.bot = bot

    async def notify_volunteers(self, message: str):
        async with AsyncSessionLocal() as session:
            # Уведомляем только волонтеров (без админов, чтобы не дублировать или конфликтовать)
            result = await session.execute(
                select(UserDB).filter(UserDB.role == "volunteer")
            )
            volunteers = result.scalars().all()
            
            for volunteer in volunteers:
                try:
                    # Убедимся, что ID - это число
                    chat_id = int(volunteer.telegram_id)
                    await self.bot.send_message(str(chat_id), message)
                except Exception as e:
                    print(f"Не удалось отправить уведомление {volunteer.telegram_id}: {e}")
