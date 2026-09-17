from src.core.base_bot import BaseBot
from src.services.request_service import RequestService

class VolunteerHandler:
    def __init__(self, bot: BaseBot, request_service: RequestService):
        self.bot = bot
        self.request_service = request_service

    async def handle_message(self, user_id: str, text: str):
        if text == "/view_requests":
            requests = await self.request_service.get_new_requests()
            if not requests:
                await self.bot.send_message(user_id, "На данный момент новых заявок нет.")
                return

            response = "Список доступных заявок:\n"
            for r in requests:
                response += f"ID: {r.id}, Категория: {r.category}, Адрес: {r.address}\n"
            await self.bot.send_message(user_id, response)

        elif text.startswith("/take "):
            try:
                request_id = int(text.split(" ")[1])
                request = await self.request_service.accept_request(request_id, user_id)
                if request:
                    await self.bot.send_message(user_id, f"Вы успешно взяли заявку #{request_id} в работу.")
                else:
                    await self.bot.send_message(user_id, "Не удалось взять заявку. Возможно, она уже принята или не существует.")
            except (ValueError, IndexError):
                await self.bot.send_message(user_id, "Неверный формат команды. Используйте: /take <ID_заявки>")
        
        elif text.startswith("/complete "):
            try:
                request_id = int(text.split(" ")[1])
                request = await self.request_service.complete_request(request_id)
                if request:
                    await self.bot.send_message(user_id, f"Заявка #{request_id} помечена как выполненная.")
                else:
                    await self.bot.send_message(user_id, "Не удалось завершить заявку.")
            except (ValueError, IndexError):
                await self.bot.send_message(user_id, "Неверный формат команды. Используйте: /complete <ID_заявки>")
        
        else:
            await self.bot.send_message(user_id, "Доступные команды: /view_requests, /take <ID>, /complete <ID>")
