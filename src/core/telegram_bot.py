from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from src.core.base_bot import BaseBot
from src.db.models import AsyncSessionLocal, UserDB
from src.services.request_service import RequestService
from src.handlers.beneficiary import BeneficiaryHandler
from src.handlers.volunteer import VolunteerHandler
from src.services.user_service import UserService
from src.services.notification_service import NotificationService
from config.settings import BOT_TOKEN, ADMIN_TELEGRAM_ID
import asyncio

class TelegramBot(BaseBot):
    def __init__(self, token):
        self.bot = Bot(token=token)
        self.dispatcher = Dispatcher()
        self.notification_service = NotificationService(self)
        self.request_service = RequestService(self.notification_service)
        self.user_service = UserService()
        self.beneficiary_handler = BeneficiaryHandler(self, self.request_service)
        self.volunteer_handler = VolunteerHandler(self, self.request_service, self.user_service)
        
        self.dispatcher.message(Command("set_admin"))(self.set_admin_command)
        self.dispatcher.message(Command("remove_admin"))(self.remove_admin_command)
        self.dispatcher.message(Command("set_volunteer"))(self.set_volunteer_command)
        self.dispatcher.message(Command("remove_volunteer"))(self.remove_volunteer_command)
        self.dispatcher.message(Command("list_users"))(self.list_users_command)
        self.dispatcher.message(Command("get_id"))(self.get_id_command)
        self.dispatcher.message(Command("admin_panel"))(self.admin_panel_command)
        self.dispatcher.callback_query()(self.handle_callback)
        self.dispatcher.message(Command("start"))(self.start_command)
        self.dispatcher.message(Command("help"))(self.help_command)
        self.dispatcher.message()(self.handle_all_messages)

    async def list_users_command(self, message: types.Message):
        user_role = await self.user_service.get_user_role(str(message.from_user.id))
        if self.user_service.get_role_power(user_role) < 2:
            await message.answer("У вас нет прав.")
            return

        users = await self.user_service.list_users()
        response = "Список пользователей:\n"
        for user in users:
            response += f"ID: {user.telegram_id} | Роль: {user.role} | Юзернейм: @{user.username or 'нет'}\n"
        await message.answer(response)

    async def get_id_command(self, message: types.Message):
        args = message.text.split()
        if len(args) == 2:
            username = args[1].replace("@", "")
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(UserDB).filter(UserDB.username == username))
                user = result.scalar_one_or_none()
                if user:
                    await message.answer(f"ID пользователя @{username}: {user.telegram_id}")
                else:
                    await message.answer(f"Пользователь @{username} не найден.")
            return

        if message.reply_to_message:
            target_id = message.reply_to_message.from_user.id
            target_username = message.reply_to_message.from_user.username
            await self.user_service.update_username(str(target_id), target_username)
            await message.answer(f"ID пользователя {('@' + target_username) if target_username else 'без тега'}: {target_id}")
            return

        await message.answer(f"Ваш ID: {message.from_user.id}")

    async def admin_panel_command(self, message: types.Message):
        user_role = await self.user_service.get_user_role(str(message.from_user.id))
        if self.user_service.get_role_power(user_role) >= 2:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Добавить волонтера", callback_data="add_vol_prompt")],
                [InlineKeyboardButton(text="Список волонтеров", callback_data="list_vol")]
            ])
            if user_role == "superadmin":
                keyboard.inline_keyboard.append([InlineKeyboardButton(text="Добавить админа", callback_data="add_adm_prompt")])
            await message.answer("Панель управления:", reply_markup=keyboard)
        else:
            await message.answer("У вас нет прав.")

    async def handle_callback(self, callback_query: types.CallbackQuery):
        await callback_query.answer(f"Нажата кнопка: {callback_query.data}")

    async def set_admin_command(self, message: types.Message):
        args = message.text.split()
        if len(args) == 2:
            success, msg = await self.user_service.set_user_role(args[1], "admin", str(message.from_user.id))
            await message.answer(msg)
        else:
            await message.answer("Использование: /set_admin <telegram_id>")

    async def remove_admin_command(self, message: types.Message):
        args = message.text.split()
        if len(args) == 2:
            success, msg = await self.user_service.remove_role(args[1], str(message.from_user.id))
            await message.answer(msg)
        else:
            await message.answer("Использование: /remove_admin <telegram_id>")

    async def set_volunteer_command(self, message: types.Message):
        args = message.text.split()
        if len(args) == 2:
            success, msg = await self.user_service.set_user_role(args[1], "volunteer", str(message.from_user.id))
            await message.answer(msg)
        else:
            await message.answer("Использование: /set_volunteer <telegram_id>")

    async def remove_volunteer_command(self, message: types.Message):
        args = message.text.split()
        if len(args) == 2:
            success, msg = await self.user_service.remove_role(args[1], str(message.from_user.id))
            await message.answer(msg)
        else:
            await message.answer("Использование: /remove_volunteer <telegram_id>")

    async def send_message(self, user_id: str, text: str, reply_markup=None):
        await self.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

    async def send_keyboard(self, user_id: str, text: str, options: list) -> int:
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=opt)] for opt in options],
            resize_keyboard=True
        )
        msg = await self.bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)
        return msg.message_id

    async def edit_message(self, user_id: str, message_id: int, text: str, reply_markup=None):
        await self.bot.edit_message_text(
            chat_id=user_id, message_id=message_id, text=text, reply_markup=reply_markup
        )

    async def on_message_received(self, user_id: str, text: str):
        pass

    async def start_command(self, message: types.Message):
        user_id = str(message.from_user.id)
        role = await self.user_service.get_user_role(user_id)
        
        welcome_text = "Здравствуйте! Это волонтерский бот помощи."
        
        if role == "beneficiary":
            welcome_text += "\n\nЕсли вам нужна помощь, нажмите /start_request, чтобы описать ситуацию."
        elif role in ["volunteer", "admin", "superadmin"]:
            welcome_text += "\n\nВы зарегистрированы как волонтер. Используйте команды для управления заявками."
            
        welcome_text += "\n\nНапишите /help, чтобы увидеть все доступные команды."
        await message.answer(welcome_text)

    async def help_command(self, message: types.Message):
        user_id = str(message.from_user.id)
        role = await self.user_service.get_user_role(user_id)
        
        if role == "beneficiary":
            help_text = "<b>🆘 Меню подопечного</b>\n\n/start_request — Создать заявку на помощь"
        elif role == "volunteer":
            help_text = (
                "<b>👷‍♂️ Меню волонтера</b>\n\n"
                "/view_requests — Список новых заявок\n"
                "/take &lt;ID&gt; — Взять заявку\n"
                "/complete &lt;ID&gt; — Завершить заявку"
            )
        elif role == "admin":
            help_text = (
                "<b>🛡 Меню администратора</b>\n\n"
                "/view_requests — Список заявок\n"
                "/set_volunteer &lt;ID&gt; — Назначить волонтера\n"
                "/remove_volunteer &lt;ID&gt; — Удалить волонтера\n"
                "/list_users — Список всех пользователей\n"
                "/get_id — Узнать ID (свой или чужой)"
            )
        elif role == "superadmin":
            help_text = (
                "<b>👑 Меню суперадмина</b>\n\n"
                "/set_admin &lt;ID&gt; — Назначить админа\n"
                "/remove_admin &lt;ID&gt; — Удалить админа\n"
                "/set_volunteer &lt;ID&gt; — Назначить волонтера\n"
                "/remove_volunteer &lt;ID&gt; — Удалить волонтера\n"
                "/list_users — Список всех пользователей\n"
                "/get_id — Узнать ID (свой или чужой)"
            )
        else:
            help_text = "Ваша роль не определена."
            
        await message.answer(help_text, parse_mode="HTML")

    async def handle_all_messages(self, message: types.Message):
        # 1. Автоматическая регистрация
        await self.user_service.update_username(str(message.from_user.id), message.from_user.username)
        
        text = message.text
        user_id = str(message.from_user.id)
        
        if not text:
            return

        # 2. Маршрутизация
        if text.startswith("/start_request"):
            await self.beneficiary_handler.handle_message(user_id, text)
        elif text.startswith("/"):
            if text.startswith(("/view_requests", "/take", "/complete")):
                await self.volunteer_handler.handle_message(user_id, text)
            else:
                await message.answer("Неизвестная команда. Напишите /help.")
        else:
            await self.beneficiary_handler.handle_message(user_id, text)

    async def run(self):
        await self.dispatcher.start_polling(self.bot)
