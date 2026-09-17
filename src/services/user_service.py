from sqlalchemy.future import select
from src.db.models import AsyncSessionLocal, UserDB
from config.settings import ADMIN_TELEGRAM_ID

class UserService:
    def get_role_power(self, role: str) -> int:
        levels = {"beneficiary": 0, "volunteer": 1, "admin": 2, "superadmin": 3}
        power = levels.get(role, 0)
        print(f"DEBUG: Role '{role}' has power {power}")
        return power

    async def get_user_role(self, telegram_id: str) -> str:
        # Принудительная проверка для главных суперадминов (список из конфига)
        print(f"DEBUG: Checking role for ID {telegram_id}. Admins: {ADMIN_TELEGRAM_ID}")
        if str(telegram_id) in [str(i).strip() for i in ADMIN_TELEGRAM_ID]:
            print("DEBUG: User is superadmin by config.")
            return "superadmin"
            
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            role = user.role if user else "beneficiary"
            print(f"DEBUG: User role in DB is {role}")
            return role

    async def set_user_role(self, target_id: str, new_role: str, actor_id: str):
        # 1. Запрет на изменение суперадмина (через env)
        if str(target_id) in ADMIN_TELEGRAM_ID:
            return False, "Нельзя изменить роль главного суперадмина."

        # 2. Получаем права
        actor_role = await self.get_user_role(actor_id)
        target_current_role = await self.get_user_role(target_id)
        
        actor_power = self.get_role_power(actor_role)
        target_current_power = self.get_role_power(target_current_role)
        new_role_power = self.get_role_power(new_role)

        # 3. Запрет: Нельзя менять роль тому, у кого права выше или равны твоим
        if target_current_power >= actor_power:
            return False, "У вас недостаточно прав для изменения этой роли."
        
        # 4. Запрет: Нельзя повышать кого-то до своего уровня или выше
        if new_role_power >= actor_power:
            return False, "Вы не можете назначать роль равную или выше вашей."

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.telegram_id == target_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.role = new_role
            else:
                new_user = UserDB(telegram_id=target_id, role=new_role)
                session.add(new_user)
            await session.commit()
            return True, "Роль успешно изменена."

    async def update_username(self, telegram_id: str, username: str):
        if not username:
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.username = username
                await session.commit()
            else:
                new_user = UserDB(telegram_id=telegram_id, username=username, role="beneficiary")
                session.add(new_user)
                await session.commit()
