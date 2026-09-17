from sqlalchemy.future import select
from src.db.models import AsyncSessionLocal, UserDB
from config.settings import ADMIN_TELEGRAM_ID

class UserService:
    def get_role_power(self, role: str) -> int:
        levels = {"beneficiary": 0, "volunteer": 1, "admin": 2, "superadmin": 3}
        return levels.get(role, 0)

    async def get_user_role(self, telegram_id: str) -> str:
        # Принудительная проверка для главных суперадминов
        if str(telegram_id) in [str(i).strip() for i in ADMIN_TELEGRAM_ID]:
            return "superadmin"
            
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.telegram_id == str(telegram_id))
            )
            user = result.scalar_one_or_none()
            return user.role if user else "beneficiary"

    async def set_user_role(self, target_id: str, new_role: str, actor_id: str):
        # 1. Запрет на изменение суперадмина
        if str(target_id) in [str(i).strip() for i in ADMIN_TELEGRAM_ID]:
            return False, "Нельзя изменить роль главного суперадмина."

        # 2. Получаем права
        actor_role = await self.get_user_role(actor_id)
        target_current_role = await self.get_user_role(target_id)
        
        actor_power = self.get_role_power(actor_role)
        target_current_power = self.get_role_power(target_current_role)
        new_role_power = self.get_role_power(new_role)

        # 3. Запрет: Нельзя менять роль тому, у кого права выше или равны твоим
        if target_current_power >= actor_power:
            return False, f"У вас недостаточно прав для изменения этой роли."
        
        # 4. Запрет: Нельзя повышать кого-то до своего уровня или выше
        if new_role_power >= actor_power:
            return False, "Вы не можете назначать роль равную или выше вашей."

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.telegram_id == str(target_id))
            )
            user = result.scalar_one_or_none()
            if user:
                user.role = new_role
            else:
                new_user = UserDB(telegram_id=str(target_id), role=new_role)
                session.add(new_user)
            await session.commit()
            return True, "Роль успешно изменена."

    async def remove_role(self, target_id: str, actor_id: str):
        if str(target_id) in [str(i).strip() for i in ADMIN_TELEGRAM_ID]:
            return False, "Нельзя изменить роль главного суперадмина."

        actor_role = await self.get_user_role(actor_id)
        target_current_role = await self.get_user_role(target_id)
        
        actor_power = self.get_role_power(actor_role)
        target_current_power = self.get_role_power(target_current_role)

        if target_current_power >= actor_power:
            return False, "У вас недостаточно прав для изменения этой роли."

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.telegram_id == str(target_id))
            )
            user = result.scalar_one_or_none()
            if user:
                user.role = "beneficiary"
                await session.commit()
                return True, "Роль успешно сброшена до подопечного."
            return False, "Пользователь не найден."

    async def list_users(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserDB))
            return result.scalars().all()

    async def update_username(self, telegram_id: str, username: str):
        if not username:
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.telegram_id == str(telegram_id))
            )
            user = result.scalar_one_or_none()
            if user:
                user.username = username
                await session.commit()
            else:
                new_user = UserDB(telegram_id=str(telegram_id), username=username, role="beneficiary")
                session.add(new_user)
                await session.commit()
