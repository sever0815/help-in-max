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
        self.dispatcher.message(Command("set_volunteer"))(self.set_volunteer_command)
        self.dispatcher.message(Command("get_id"))(self.get_id_command)
        self.dispatcher.message(Command("admin_panel"))(self.admin_panel_command)
        self.dispatcher.callback_query()(self.handle_callback)
        self.dispatcher.message(Command("start"))(self.start_command)
        self.dispatcher.message(Command("help"))(self.help_command)
        self.dispatcher.message()(self.handle_all_messages)

    async def get_id_command(self, message: types.Message):
        user_role = await self.user_service.get_user_role(str(message.from_user.id))
        if self.user_service.get_role_power(user_role) < 2:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return

        args = message.text.split()
        
        # 1. Если передали тег: /get_id @username
        if len(args) == 2:
            username = args[1].replace("@", "")
            # Поиск в базе по username
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(UserDB).filter(UserDB.username == username))
                user = result.scalar_one_or_none()
                if user:
                    await message.answer(f"ID пользователя @{username}: {user.telegram_id}")
                else:
                    await message.answer(f"Пользователь @{username} не найден в базе данных.")
            return

        # 2. Если ответили на сообщение
        if message.reply_to_message:
            target_id = message.reply_to_message.from_user.id
            target_username = message.reply_to_message.from_user.username
            # Сохраняем username в базу, если еще нет
            await self.user_service.update_username(str(target_id), target_username)
            await message.answer(f"ID пользователя {('@' + target_username) if target_username else 'без тега'}: {target_id}")
            return

        # 3. Иначе показываем свой ID
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
        # Временная заглушка для обработки нажатий кнопок
        await callback_query.answer(f"Нажата кнопка: {callback_query.data}")

    async def set_admin_command(self, message: types.Message):
        # Проверяем, есть ли уже суперадмины
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserDB).filter(UserDB.role == "superadmin"))
            superadmins = result.scalars().all()
            
        if not superadmins:
            # Если суперадминов нет — первый, кто пишет, становится суперадмином
            await self.user_service.set_user_role(str(message.from_user.id), "superadmin", str(message.from_user.id))
            await message.answer(f"Суперадмин не найден. Пользователь {message.from_user.username} назначен первым суперадмином.")
        else:
            # Если суперадмины есть — только суперадмин может назначать других
            user_role = await self.user_service.get_user_role(str(message.from_user.id))
            if user_role == "superadmin":
                args = message.text.split()
                if len(args) == 2:
                    target_id = args[1]
                    await self.user_service.set_user_role(target_id, "admin", str(message.from_user.id))
                    await message.answer(f"Пользователь {target_id} назначен администратором.")
                else:
                    await message.answer("Использование: /set_admin <telegram_id>")
            else:
                await message.answer("У вас нет прав для выполнения этой команды.")

    async def set_volunteer_command(self, message: types.Message):
        # Админы и суперадмины могут назначать волонтеров
        args = message.text.split()
        if len(args) == 2:
            target_id = args[1]
            success, msg = await self.user_service.set_user_role(target_id, "volunteer", str(message.from_user.id))
            if success:
                await message.answer(f"Пользователь {target_id} назначен волонтером.")
            else:
                await message.answer(msg)
        else:
            await message.answer("Использование: /set_volunteer <telegram_id>")

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
            help_text = (
                "🆘 **Меню подопечного**\n\n"
                "/start_request — Создать заявку на помощь"
            )
        elif role == "volunteer":
            help_text = (
                "👷‍♂️ **Меню волонтера**\n\n"
                "/view_requests — Список новых заявок\n"
                "/take <ID> — Взять заявку\n"
                "/complete <ID> — Завершить заявку"
            )
        elif role == "admin":
            help_text = (
                "🛡 **Меню администратора**\n\n"
                "/view_requests — Список заявок\n"
                "/set_volunteer <ID> — Назначить волонтера"
            )
        elif role == "superadmin":
            help_text = (
                "👑 **Меню суперадмина**\n\n"
                "/set_admin <ID> — Назначить админа\n"
                "/set_volunteer <ID> — Назначить волонтера\n"
                "/get_id — Узнать ID (свой или чужой)"
            )
        else:
            help_text = "Ваша роль не определена. Обратитесь к администратору."
            
        await message.answer(help_text, parse_mode="Markdown")

    async def handle_all_messages(self, message: types.Message):
        text = message.text
        user_id = str(message.from_user.id)
        
        # Маршрутизация между хендлерами
        if text.startswith("/start_request"):
            await self.beneficiary_handler.handle_message(user_id, text)
        elif text.startswith("/"):
            await self.volunteer_handler.handle_message(user_id, text)
        else:
            await self.beneficiary_handler.handle_message(user_id, text)

    async def run(self):
        await self.dispatcher.start_polling(self.bot)
