import logging
from src.core.base_bot import BaseBot
from src.services.request_service import RequestService
from src.services.user_service import UserService

logger = logging.getLogger(__name__)

class VolunteerHandler:
    def __init__(self, bot: BaseBot, request_service: RequestService, user_service: UserService):
        self.bot = bot
        self.request_service = request_service
        self.user_service = user_service

    async def _is_authorized(self, user_id: str) -> bool:
        role = await self.user_service.get_user_role(user_id)
        return role in ["volunteer", "admin"]

    async def handle_message(self, user_id: str, text: str):
        if not await self._is_authorized(user_id):
            await self.bot.send_message(user_id, "У вас нет прав для выполнения этой команды.")
            return

        if text.startswith("/view_requests"):
            await self._handle_view_requests(user_id)

        elif text.startswith("/take"):
            await self._handle_take(user_id, text)

        elif text.startswith("/complete"):
            await self._handle_complete(user_id, text)

    async def _handle_view_requests(self, user_id: str):
        """Показать список заявок с кнопками."""
        requests = await self.request_service.get_active_requests(volunteer_id=user_id)
        if not requests:
            await self.bot.send_message(user_id, "Заявок нет")
            return

        # Получаем ФИО пользователей
        user_names = {}
        for r in requests:
            uid = r.beneficiary_id
            if uid not in user_names:
                from src.db.models import AsyncSessionLocal, UserDB
                from sqlalchemy.future import select
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(UserDB).filter(UserDB.platform_user_id == str(uid))
                    )
                    user = result.scalar_one_or_none()
                    user_names[uid] = user.full_name if user and user.full_name else "—"

        # Сортируем: активные (принятые этим волонтёром) первыми
        active_requests = [r for r in requests if r.volunteer_id == str(user_id) and r.status == "accepted"]
        other_requests = [r for r in requests if r not in active_requests]
        sorted_requests = active_requests + other_requests

        status_map = {"new": "Ожидает", "accepted": "Принята", "completed": "Завершена", "cancelled": "Отменена"}
        category_map = {"products": "Продукты", "walk": "Прогулка", "cleaning": "Уборка", "other": "Другое"}

        for r in sorted_requests:
            name = user_names.get(r.beneficiary_id, "—")
            phone = r.phone or "—"
            status_text = status_map.get(r.status, r.status)
            category_text = category_map.get(r.category, r.category)

            request_info = (f"📋 <b>Заявка #{r.id}</b>\n\n"
                           f"👕 Категория: {category_text}\n"
                           f"📍 Адрес: {r.address}\n"
                           f"🕐 Время: {r.scheduled_time}\n"
                           f"📞 Телефон: {phone}\n"
                           f"📝 Детали: {r.description or '—'}\n"
                           f"👤 ФИО: {name}\n"
                           f"📊 Статус: {status_text}")

            # Кнопки в зависимости от статуса
            if r.status == "new":
                keyboard = [
                    [{"type": "callback", "text": "Принять", "payload": f"accept_request:{r.id}"}]
                ]
            elif r.status == "accepted" and r.volunteer_id == str(user_id):
                keyboard = [
                    [{"type": "callback", "text": "Завершить", "payload": f"complete_request:{r.id}"}],
                    [{"type": "callback", "text": "Отклонить", "payload": f"reject_request:{r.id}"}]
                ]
            else:
                keyboard = None

            await self.bot.send_message(user_id, request_info, reply_markup=keyboard)

    async def _handle_take(self, user_id: str, text: str):
        """Принять заявку по ID."""
        parts = text.split()
        if len(parts) < 2:
            await self.bot.send_message(user_id, "Использование: /take <ID_заявки>")
            return
        try:
            request_id = int(parts[1])
            request = await self.request_service.accept_request(request_id, user_id)
            if request:
                await self.bot.send_message(user_id, f"Вы успешно взяли заявку #{request_id} в работу.")
            else:
                await self.bot.send_message(user_id, "Не удалось взять заявку. Возможно, она уже принята или не существует.")
        except (ValueError, IndexError):
            await self.bot.send_message(user_id, "Неверный формат команды. Используйте: /take <ID_заявки>")

    async def _handle_complete(self, user_id: str, text: str):
        """Завершить заявку по ID."""
        parts = text.split()
        if len(parts) < 2:
            await self.bot.send_message(user_id, "Использование: /complete <ID_заявки>")
            return
        try:
            request_id = int(parts[1])
            request = await self.request_service.complete_request(request_id)
            if request:
                await self.bot.send_message(user_id, f"Заявка #{request_id} помечена как выполненная.")
            else:
                await self.bot.send_message(user_id, "Не удалось завершить заявку.")
        except (ValueError, IndexError):
            await self.bot.send_message(user_id, "Неверный формат команды. Используйте: /complete <ID_заявки>")
