from enum import Enum
from typing import Dict, Any
from src.core.base_bot import BaseBot
from src.services.request_service import RequestService

class BeneficiaryState(Enum):
    IDLE = "idle"
    CHOOSING_CATEGORY = "choosing_category"
    DESCRIBING_SITUATION = "describing_situation"
    PROVIDING_ADDRESS = "providing_address"

class BeneficiaryHandler:
    def __init__(self, bot: BaseBot, request_service: RequestService):
        self.bot = bot
        self.request_service = request_service
        # Временное хранилище состояний пользователей
        self.user_states: Dict[str, Dict[str, Any]] = {}

    async def handle_message(self, user_id: str, text: str):
        state_data = self.user_states.get(user_id, {"state": BeneficiaryState.IDLE})
        state = state_data["state"]

        if text == "/help":
            self.user_states[user_id] = {"state": BeneficiaryState.CHOOSING_CATEGORY}
            await self.bot.send_keyboard(
                user_id, 
                "Какая помощь вам нужна?", 
                ["Продукты", "Прогулка", "Уборка", "Другое"]
            )
            return

        # Маппинг категорий
        category_map = {
            "Продукты": "products",
            "Прогулка": "walk",
            "Уборка": "cleaning",
            "Другое": "other"
        }

        if state == BeneficiaryState.CHOOSING_CATEGORY:
            category_internal = category_map.get(text, "other")
            self.user_states[user_id] = {"state": BeneficiaryState.DESCRIBING_SITUATION, "category": category_internal}
            await self.bot.send_message(user_id, "Пожалуйста, опишите вашу ситуацию подробнее.")
        
        elif state == BeneficiaryState.DESCRIBING_SITUATION:
            state_data["description"] = text
            state_data["state"] = BeneficiaryState.PROVIDING_ADDRESS
            await self.bot.send_message(user_id, "Теперь укажите, пожалуйста, ваш адрес.")
        
        elif state == BeneficiaryState.PROVIDING_ADDRESS:
            category = state_data.get("category")
            description = state_data.get("description")
            address = text
            
            await self.request_service.create_request(user_id, category, description, address)
            self.user_states[user_id] = {"state": BeneficiaryState.IDLE}
            await self.bot.send_message(user_id, "Спасибо! Ваша заявка принята и передана волонтерам.")
