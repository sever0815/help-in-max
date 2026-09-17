from sqlalchemy.future import select
from sqlalchemy import or_
from src.db.models import AsyncSessionLocal, UserDB
from src.core.base_bot import BaseBot

class NotificationService:
    def __init__(self, bot: BaseBot):
        self.bot = bot

    async def notify_volunteers(self, message: str):
        async with AsyncSessionLocal() as session:
            # Уведомляем только тех, у кого роль 'volunteer'
            # И дополнительно фильтруем, чтобы telegram_id был числовым (на всякий случай)
            result = await session.execute(
                select(UserDB).filter(UserDB.role == "volunteer")
            )
            volunteers = result.scalars().all()
            
            for volunteer in volunteers:
                try:
                    # Проверяем, можно ли преобразовать в int
                    if volunteer.telegram_id.isdigit():
                        await self.bot.send_message(volunteer.telegram_id, message)
                    else:
                        print(f"Пропуск пользователя {volunteer.telegram_id}: ID не является числом")
                except Exception as e:
                    print(f"Не удалось отправить уведомление {volunteer.telegram_id}: {e}")
