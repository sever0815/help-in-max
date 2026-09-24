from enum import Enum
from typing import Dict, Any
from src.core.base_bot import BaseBot
from src.services.request_service import RequestService

class BeneficiaryState(Enum):
    IDLE = "idle"
    CHOOSING_CATEGORY = "choosing_category"
    DESCRIBING_SITUATION = "describing_situation"
    PROVIDING_ADDRESS = "providing_address"
    CHOOSING_TIME = "choosing_time"
    CONFIRMATION = "confirmation"

class BeneficiaryHandler:
    def __init__(self, bot: BaseBot, request_service: RequestService):
        self.bot = bot
        self.request_service = request_service
        # Временное хранилище состояний пользователей: {user_id: {"state": ..., "last_msg_id": ..., "last_text": ...}}
        self.user_states: Dict[str, Dict[str, Any]] = {}

    async def _clear_prev_keyboard(self, user_id: str):
        state_data = self.user_states.get(user_id)
        if state_data and state_data.get("last_msg_id"):
            try:
                await self.bot.edit_message(user_id, state_data["last_msg_id"], text=state_data["last_text"], reply_markup=None)
            except Exception:
                pass
            state_data["last_msg_id"] = None
            state_data["last_text"] = None

    async def handle_callback(self, user_id: str, payload: str):
        """Обработка нажатий inline-кнопок: как текст, но только точные варианты."""
        await self.handle_message(user_id, payload)

    async def handle_message(self, user_id: str, text: str):
        state_data = self.user_states.get(user_id, {"state": BeneficiaryState.IDLE})
        state = state_data["state"]

        if text == "/start_request":
            await self._clear_prev_keyboard(user_id)
            self.user_states[user_id] = {"state": BeneficiaryState.CHOOSING_CATEGORY}

            text_q = "Какая помощь вам нужна?"
            msg_id = await self.bot.send_keyboard(
                user_id,
                text_q,
                ["Продукты", "Прогулка", "Уборка", "Другое"]
            )
            self.user_states[user_id]["last_msg_id"] = msg_id
            self.user_states[user_id]["last_text"] = text_q
            return

        # Маппинг категорий
        category_map = {
            "Продукты": "products",
            "Прогулка": "walk",
            "Уборка": "cleaning",
            "Другое": "other"
        }

        if state == BeneficiaryState.CHOOSING_CATEGORY:
            await self._clear_prev_keyboard(user_id)
            category_internal = category_map.get(text, "other")
            self.user_states[user_id] = {"state": BeneficiaryState.DESCRIBING_SITUATION, "category": category_internal}
            await self.bot.send_message(user_id, "Пожалуйста, опишите вашу ситуацию подробнее.")

        elif state == BeneficiaryState.DESCRIBING_SITUATION:
            state_data["description"] = text
            state_data["state"] = BeneficiaryState.PROVIDING_ADDRESS
            await self.bot.send_message(user_id, "Теперь укажите, пожалуйста, ваш адрес.")

        elif state == BeneficiaryState.PROVIDING_ADDRESS:
            state_data["address"] = text
            state_data["state"] = BeneficiaryState.CHOOSING_TIME

            text_q = "Когда вам нужна помощь?"
            msg_id = await self.bot.send_keyboard(user_id, text_q, ["Сейчас", "Через час", "Указать время"])
            state_data["last_msg_id"] = msg_id
            state_data["last_text"] = text_q

        elif state == BeneficiaryState.CHOOSING_TIME:
            await self._clear_prev_keyboard(user_id)
            state_data["scheduled_time"] = text
            state_data["state"] = BeneficiaryState.CONFIRMATION

            summary = (f"Проверьте данные вашей заявки:\n"
                       f"Категория: {state_data['category']}\n"
                       f"Описание: {state_data['description']}\n"
                       f"Адрес: {state_data['address']}\n"
                       f"Время: {state_data['scheduled_time']}\n\n"
                       "Отправить заявку?")

            msg_id = await self.bot.send_keyboard(user_id, summary, ["Подтвердить", "Отмена"])
            state_data["last_msg_id"] = msg_id
            state_data["last_text"] = summary

        elif state == BeneficiaryState.CONFIRMATION:
            await self._clear_prev_keyboard(user_id)
            if text == "Подтвердить":
                await self.request_service.create_request(
                    user_id,
                    state_data.get("category"),
                    state_data.get("description"),
                    state_data.get("address"),
                    state_data.get("scheduled_time")
                )
                self.user_states[user_id] = {"state": BeneficiaryState.IDLE}
                await self.bot.send_message(user_id, "Спасибо! Ваша заявка принята и передана волонтерам.")
            elif text == "Отмена":
                self.user_states[user_id] = {"state": BeneficiaryState.IDLE}
                await self.bot.send_message(user_id, "Заявка отменена.")
            else:
                await self.bot.send_message(user_id, "Пожалуйста, выберите 'Подтвердить' или 'Отмена' на клавиатуре.")
