from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from src.core.base_bot import BaseBot
from src.services.request_service import RequestService
from src.handlers.beneficiary import BeneficiaryHandler
from src.handlers.volunteer import VolunteerHandler
from config.settings import BOT_TOKEN
import asyncio

class TelegramBot(BaseBot):
    def __init__(self, token):
        self.bot = Bot(token=token)
        self.dispatcher = Dispatcher()
        self.request_service = RequestService()
        self.beneficiary_handler = BeneficiaryHandler(self, self.request_service)
        self.volunteer_handler = VolunteerHandler(self, self.request_service)
        
        self.dispatcher.message(Command("start"))(self.start_command)
        self.dispatcher.message()(self.handle_all_messages)

    async def send_message(self, user_id: str, text: str, reply_markup=None):
        await self.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

    async def send_keyboard(self, user_id: str, text: str, options: list):
        # В aiogram клавиатуры реализуются через ReplyKeyboardMarkup
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=opt)] for opt in options],
            resize_keyboard=True
        )
        await self.bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)

    async def on_message_received(self, user_id: str, text: str):
        # Этот метод не используется напрямую в Telegram, так как мы используем хендлеры aiogram
        pass

    async def start_command(self, message: types.Message):
        await message.answer("Привет! Я волонтерский бот. Напишите /help для начала работы.")

    async def handle_all_messages(self, message: types.Message):
        text = message.text
        user_id = str(message.from_user.id)
        
        # Маршрутизация между хендлерами (в реальном боте стоит сделать умнее)
        if text.startswith("/"):
            await self.volunteer_handler.handle_message(user_id, text)
        else:
            await self.beneficiary_handler.handle_message(user_id, text)

    async def run(self):
        await self.dispatcher.start_polling(self.bot)
