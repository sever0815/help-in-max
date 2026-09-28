from enum import Enum
from typing import Dict, Any
from src.core.base_bot import BaseBot
from src.services.request_service import RequestService

class BeneficiaryState(Enum):
    IDLE = "idle"
    CHOOSING_HELP_TYPE = "choosing_help_type"
    PROVIDING_ADDRESS = "providing_address"
    CHOOSING_TIME = "choosing_time"
    CHOOSING_TIME_CUSTOM = "choosing_time_custom"
    ASKING_DETAILS = "asking_details"
    CONFIRMATION = "confirmation"

class BeneficiaryHandler:
    def __init__(self, bot: BaseBot, request_service: RequestService):
        self.bot = bot
        self.request_service = request_service
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
        await self.handle_message(user_id, payload)

    async def handle_message(self, user_id: str, text: str):
        state_data = self.user_states.get(user_id, {"state": BeneficiaryState.IDLE})
        state = state_data["state"]

        # === НАЧАЛО /start_request ===
        if text == "/start_request":
            await self._clear_prev_keyboard(user_id)
            self.user_states[user_id] = {"state": BeneficiaryState.CHOOSING_HELP_TYPE}
            text_q = "Какую помощь вам нужна? Выберите тип или укажите свой:"
            msg_id = await self.bot.send_keyboard(
                user_id,
                text_q,
                ["Продукты", "Прогулка", "Уборка", "Другое", "Свой вариант"]
            )
            state_data["last_msg_id"] = msg_id
            state_data["last_text"] = text_q
            return

        # === КАРТА КАТЕГОРИЙ ===
        category_map = {
            "Продукты": "products",
            "Прогулка": "walk",
            "Уборка": "cleaning",
            "Другое": "other"
        }

        # === ШАГ 1: Выбор типа помощи ===
        if state == BeneficiaryState.CHOOSING_HELP_TYPE:
            await self._clear_prev_keyboard(user_id)
            if text == "Свой вариант":
                state_data["state"] = BeneficiaryState.CHOOSING_HELP_TYPE_CUSTOM
                await self.bot.send_message(user_id, "Укажите тип помощи:")
            else:
                category = category_map.get(text, "other")
                state_data["category"] = category
                state_data["state"] = BeneficiaryState.PROVIDING_ADDRESS
                await self.bot.send_message(user_id, "Укажите, пожалуйста, ваш адрес.")
            self.user_states[user_id] = state_data
            return

        # === ШАГ 1b: Свой тип помощи (текстовый ввод) ===
        if state == BeneficiaryState.CHOOSING_HELP_TYPE_CUSTOM:
            state_data["category"] = text.lower().replace(" ", "_")
            state_data["state"] = BeneficiaryState.PROVIDING_ADDRESS
            await self.bot.send_message(user_id, "Укажите, пожалуйста, ваш адрес.")
            self.user_states[user_id] = state_data
            return

        # === ШАГ 2: Адрес ===
        if state == BeneficiaryState.PROVIDING_ADDRESS:
            state_data["address"] = text
            state_data["state"] = BeneficiaryState.CHOOSING_TIME
            time_buttons = ["Сейчас", "Через 10 мин", "Через 30 мин", "Через 1 час", "Через 2 часа", "Через 3 часа", "Указать время"]
            msg_id = await self.bot.send_keyboard(user_id, "Когда вам нужна помощь? Выберите время или укажите своё:", time_buttons)
            state_data["last_msg_id"] = msg_id
            state_data["last_text"] = "Когда вам нужна помощь?"
            self.user_states[user_id] = state_data
            return

        # === ШАГ 3: Время (выбор из вариантов) ===
        if state == BeneficiaryState.CHOOSING_TIME:
            await self._clear_prev_keyboard(user_id)
            if text == "Указать время":
                state_data["state"] = BeneficiaryState.CHOOSING_TIME_CUSTOM
                await self.bot.send_message(user_id, "Введите желаемое время (например: 14:30, завтра 10:00, через 45 минут):")
                self.user_states[user_id] = state_data
                return
            time_map = {
                "Сейчас": "сейчас",
                "Через 10 мин": "через 10 минут",
                "Через 30 мин": "через 30 минут",
                "Через 1 час": "через 1 час",
                "Через 2 часа": "через 2 часа",
                "Через 3 часа": "через 3 часа"
            }
            state_data["scheduled_time"] = time_map.get(text, text)
            state_data["state"] = BeneficiaryState.ASKING_DETAILS
            await self.bot.send_message(user_id, "Есть ли что-то дополнительное, что стоит учесть? (можно пропустить)")
            msg_id = await self.bot.send_keyboard(user_id, "Дополнительные детали", ["Да, есть", "Нет, спасибо"])
            state_data["last_msg_id"] = msg_id
            state_data["last_text"] = "Есть ли что-то дополнительное?"
            self.user_states[user_id] = state_data
            return

        # === ШАГ 3b: Ввод своего времени ===
        if state == BeneficiaryState.CHOOSING_TIME_CUSTOM:
            state_data["scheduled_time"] = text
            state_data["state"] = BeneficiaryState.ASKING_DETAILS
            await self.bot.send_message(user_id, "Есть ли что-то дополнительное, что стоит учесть? (можно пропустить)")
            msg_id = await self.bot.send_keyboard(user_id, "Дополнительные детали", ["Да, есть", "Нет, спасибо"])
            state_data["last_msg_id"] = msg_id
            state_data["last_text"] = "Есть ли что-то дополнительное?"
            self.user_states[user_id] = state_data
            return

        # === ШАГ 4: Дополнительные детали ===
        if state == BeneficiaryState.ASKING_DETAILS:
            await self._clear_prev_keyboard(user_id)
            if text == "Да, есть":
                await self.bot.send_message(user_id, "Опишите дополнительные детали:")
                state_data["state"] = BeneficiaryState.DESCRIBING_DETAILS
            else:
                state_data["details"] = ""
                state_data["state"] = BeneficiaryState.CONFIRMATION
                await self._show_confirmation(user_id, state_data)
            self.user_states[user_id] = state_data
            return

        # === ШАГ 4b: Ввод дополнительных деталей ===
        if state == BeneficiaryState.DESCRIBING_DETAILS:
            state_data["details"] = text
            state_data["state"] = BeneficiaryState.CONFIRMATION
            await self._show_confirmation(user_id, state_data)
            self.user_states[user_id] = state_data
            return

        # === ШАГ 5: Подтверждение ===
        if state == BeneficiaryState.CONFIRMATION:
            if text == "Отправить" or text == "Отправить заявку":
                await self.request_service.create_request(
                    user_id,
                    state_data.get("category"),
                    state_data.get("details", ""),
                    state_data.get("address"),
                    state_data.get("scheduled_time")
                )
                self.user_states[user_id] = {"state": BeneficiaryState.IDLE}
                await self.bot.send_message(user_id, "Спасибо! Ваша заявка принята и передана волонтёрам.")
            elif text == "Изменить" or text in ("Изменить тип", "Изменить адрес", "Изменить время", "Изменить детали"):
                if text in ("Изменить тип", "Изменить адрес", "Изменить время", "Изменить детали"):
                    # Переходим к нужному шагу
                    if text == "Изменить тип":
                        state_data["state"] = BeneficiaryState.CHOOSING_HELP_TYPE
                        await self.bot.send_message(user_id, "Какую помощь вам нужна? Выберите тип или укажите свой:")
                        msg_id = await self.bot.send_keyboard(
                            user_id,
                            "Какую помощь вам нужна?",
                            ["Продукты", "Прогулка", "Уборка", "Другое", "Свой вариант"]
                        )
                        state_data["last_msg_id"] = msg_id
                    elif text == "Изменить адрес":
                        state_data["state"] = BeneficiaryState.PROVIDING_ADDRESS
                        await self.bot.send_message(user_id, "Укажите, пожалуйста, ваш адрес.")
                    elif text == "Изменить время":
                        state_data["state"] = BeneficiaryState.CHOOSING_TIME
                        await self.bot.send_message(user_id, "Когда вам нужна помощь?")
                        time_buttons = ["Сейчас", "Через 10 мин", "Через 30 мин", "Через 1 час", "Через 2 часа", "Указать время"]
                        msg_id = await self.bot.send_keyboard(user_id, "Выберите время или укажите своё:", time_buttons)
                        state_data["last_msg_id"] = msg_id
                        state_data["last_text"] = "Когда вам нужна помощь?"
                    elif text == "Изменить детали":
                        state_data["state"] = BeneficiaryState.ASKING_DETAILS
                        await self.bot.send_message(user_id, "Есть ли что-то дополнительное?")
                        msg_id = await self.bot.send_keyboard(user_id, "Дополнительные детали", ["Да, есть", "Нет, спасибо"])
                        state_data["last_msg_id"] = msg_id
                        state_data["last_text"] = "Есть ли что-то дополнительное?"
                    self.user_states[user_id] = state_data
                else:
                    # text == "Изменить" — показать опции редактирования
                    await self._show_edit_options(user_id, state_data)
            elif text == "Отклонить":
                self.user_states[user_id] = {"state": BeneficiaryState.IDLE}
                await self.bot.send_message(user_id, "Заявка отменена.")
            else:
                await self.bot.send_message(user_id, "Пожалуйста, выберите 'Отправить', 'Изменить' или 'Отклонить'.")
            return

    async def _show_confirmation(self, user_id: str, state_data: dict):
        s = state_data
        summary = (f"📋 <b>Проверьте заявку:</b>\n\n"
                   f"👕 Тип помощи: <b>{s.get('category', '—')}</b>\n"
                   f"📍 Адрес: <b>{s.get('address', '—')}</b>\n"
                   f"🕐 Время: <b>{s.get('scheduled_time', '—')}</b>\n"
                   f"📝 Детали: <b>{s.get('details', '—')}</b>\n\n"
                   "Отправить заявку?")
        msg_id = await self.bot.send_keyboard(
            user_id,
            summary,
            ["Отправить", "Изменить", "Отклонить"]
        )
        state_data["last_msg_id"] = msg_id
        state_data["last_text"] = summary

    async def _show_edit_options(self, user_id: str, state_data: dict):
        options = [
            [{"type": "callback", "text": "Изменить тип", "payload": "Изменить тип"}],
            [{"type": "callback", "text": "Изменить адрес", "payload": "Изменить адрес"}],
            [{"type": "callback", "text": "Изменить время", "payload": "Изменить время"}],
            [{"type": "callback", "text": "Изменить детали", "payload": "Изменить детали"}],
            [{"type": "callback", "text": "Отмена", "payload": "Отмена"}]
        ]
        await self.bot.send_message(user_id, "Что хотите изменить?", reply_markup=options)
