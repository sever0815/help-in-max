from sqlalchemy.future import select
from src.db.models import AsyncSessionLocal, UserDB
from config.settings import ADMIN_USER_IDS

class UserService:
    def get_role_power(self, role: str) -> int:
        levels = {"blocked": -1, "beneficiary": 0, "volunteer": 1, "admin": 2, "superadmin": 3}
        return levels.get(role, 0)

    @staticmethod
    def _is_main_superadmin(platform_user_id: str) -> bool:
        return str(platform_user_id) in [str(i).strip() for i in ADMIN_USER_IDS]

    async def get_user_role(self, platform_user_id: str) -> str:
        # Принудительная проверка для главных суперадминов
        if self._is_main_superadmin(platform_user_id):
            return "superadmin"

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.platform_user_id == str(platform_user_id))
            )
            user = result.scalar_one_or_none()
            return user.role if user else "beneficiary"

    async def set_user_role(self, target_id: str, new_role: str, actor_id: str):
        # 1. Запрет на изменение суперадмина
        if self._is_main_superadmin(target_id):
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
        # (админ может назначать волонтеров, но не других админов)
        if new_role_power >= actor_power and new_role != "volunteer":
            return False, "Вы не можете назначать роль равную или выше вашей."

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.platform_user_id == str(target_id))
            )
            user = result.scalar_one_or_none()
            if user:
                user.role = new_role
            else:
                new_user = UserDB(platform_user_id=str(target_id), role=new_role)
                session.add(new_user)
            await session.commit()
            return True, "Роль успешно изменена."

    async def remove_role(self, target_id: str, actor_id: str):
        if self._is_main_superadmin(target_id):
            return False, "Нельзя изменить роль главного суперадмина."

        actor_role = await self.get_user_role(actor_id)
        target_current_role = await self.get_user_role(target_id)

        actor_power = self.get_role_power(actor_role)
        target_current_power = self.get_role_power(target_current_role)

        if target_current_power >= actor_power:
            return False, "У вас недостаточно прав для изменения этой роли."

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.platform_user_id == str(target_id))
            )
            user = result.scalar_one_or_none()
            if user:
                user.role = "beneficiary"
                await session.commit()
                return True, "Роль успешно сброшена до подопечного."
            return False, "Пользователь не найден."

    async def set_user_name(self, target_id: str, full_name: str, actor_id: str):
        """Установить ФИО пользователя (только для admin/superadmin)."""
        actor_role = await self.get_user_role(actor_id)
        actor_power = self.get_role_power(actor_role)
        if actor_power < 2:
            return False, "У вас нет прав для выполнения этой команды."

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.platform_user_id == str(target_id))
            )
            user = result.scalar_one_or_none()
            if user:
                user.full_name = full_name
                await session.commit()
                return True, f"ФИО пользователя {target_id} обновлено: {full_name}"
            else:
                new_user = UserDB(platform_user_id=str(target_id), full_name=full_name, role="beneficiary")
                session.add(new_user)
                await session.commit()
                return True, f"Пользователь {target_id} добавлен с ФИО: {full_name}"

    async def list_users(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserDB))
            return result.scalars().all()

    async def update_username(self, platform_user_id: str, username: str, full_name: str = None):
        from config.settings import ADMIN_USER_IDS
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.platform_user_id == str(platform_user_id))
            )
            user = result.scalar_one_or_none()
            if user:
                if username and user.username != username:
                    user.username = username
                if full_name and user.full_name != full_name:
                    user.full_name = full_name
                await session.commit()
            else:
                # Определяем роль при регистрации
                if str(platform_user_id) in [str(i).strip() for i in ADMIN_USER_IDS]:
                    role = "superadmin"
                else:
                    role = "beneficiary"
                new_user = UserDB(
                    platform_user_id=str(platform_user_id),
                    username=username,
                    full_name=full_name,
                    role=role
                )
                session.add(new_user)
                await session.commit()
