from sqlalchemy.future import select
from sqlalchemy import or_
import logging
from src.db.models import AsyncSessionLocal, UserDB
from src.core.base_bot import BaseBot

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, bot: BaseBot):
        self.bot = bot

    async def notify_volunteers(self, message: str):
        async with AsyncSessionLocal() as session:
            # Уведомляем только тех, у кого роль 'volunteer'
            result = await session.execute(
                select(UserDB).filter(UserDB.role == "volunteer")
            )
            volunteers = result.scalars().all()

            for volunteer in volunteers:
                try:
                    # MAX user_id — всегда число; пропускаем мусорные ID
                    if volunteer.platform_user_id.isdigit():
                        await self.bot.send_message(volunteer.platform_user_id, message)
                    else:
                        logger.info(f"Пропуск пользователя {volunteer.platform_user_id}: ID не является числом")
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление {volunteer.platform_user_id}: {e}")
