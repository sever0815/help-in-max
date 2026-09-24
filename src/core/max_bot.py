import asyncio
import logging
import httpx
from typing import Any, Dict, List, Optional
from sqlalchemy.future import select
from src.core.base_bot import BaseBot
from src.db.models import AsyncSessionLocal, UserDB
from src.services.request_service import RequestService
from src.handlers.beneficiary import BeneficiaryHandler
from src.handlers.volunteer import VolunteerHandler
from src.services.user_service import UserService
from src.services.notification_service import NotificationService
from config.settings import BOT_TOKEN

logger = logging.getLogger(__name__)

class MaxBot(BaseBot):
    def __init__(self, token: str, base_url: str = "https://platform-api2.max.ru"):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.notification_service = NotificationService(self)
        self.request_service = RequestService(self.notification_service)
        self.user_service = UserService()
        self.beneficiary_handler = BeneficiaryHandler(self, self.request_service)
        self.volunteer_handler = VolunteerHandler(self, self.request_service, self.user_service)

        # verify=False обходит проблему с сертификатом Минцифры
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": self.token,
                "Content-Type": "application/json"
            },
            timeout=30.0,
            verify=False
        )
        self.running = False
        self.marker: Optional[int] = None

    # ---------- Низкоуровневые вызовы API ----------

    async def _api_call(self, method: str, endpoint: str, *, params: Optional[dict] = None, json_body: Optional[dict] = None) -> Optional[dict]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = await self.client.request(method, url, params=params, json=json_body)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("success") is False:
                logger.error(f"MAX API error on {endpoint}: {data}")
                return None
            return data
        except Exception as e:
            logger.error(f"Error calling {method} {endpoint}: {e}")
            return None

    def _build_keyboard(self, buttons: List[List[Dict[str, str]]]) -> list:
        return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]

    # ---------- Реализация BaseBot ----------

    async def send_message(self, user_id: str, text: str, reply_markup: Optional[Any] = None) -> int:
        """Отправляет текстовое сообщение пользователю через MAX API."""
        payload: Dict[str, Any] = {"text": text, "format": "html"}
        if reply_markup is not None:
            payload["attachments"] = self._build_keyboard(reply_markup)
        data = await self._api_call(
            "POST", "/messages",
            params={"user_id": user_id},
            json_body=payload
        )
        message = (data or {}).get("message") or {}
        mid = message.get("body", {}).get("mid") or message.get("mid") or 1
        return mid

    async def pin_message(self, message_id: Any) -> bool:
        """Закрепляет сообщение в чате."""
        data = await self._api_call("PUT", f"/messages/{message_id}/pin")
        return data is not None

    async def send_keyboard(self, user_id: str, text: str, options: List[str]) -> Any:
        """
        Отправляет сообщение с inline-клавиатурой MAX (кнопки type='callback').
        Возвращает mid сообщения (для последующего редактирования).
        """
        rows = [[{"type": "callback", "text": opt, "payload": opt}] for opt in options]
        return await self.send_message(user_id, text, reply_markup=rows)

    async def answer_callback(self, callback_id: str, text: Optional[str] = None) -> None:
        """Подтверждает нажатие кнопки (убирает индикатор загрузки на клиенте)."""
        body: Dict[str, Any] = {"callback_id": callback_id}
        if text:
            body["notification"] = text
        await self._api_call("POST", "/answers", json_body=body)

    async def edit_message(self, user_id: str, message_id: Any, text: str, reply_markup=None):
        """Редактирует сообщение бота; при неудаче отправляет новое.

        При reply_markup=None клавиатура удаляется: по документации MAX
        пустой массив attachments снимает все вложения.
        """
        payload: Dict[str, Any] = {"text": text, "format": "html", "attachments": []}
        if reply_markup is not None:
            payload["attachments"] = self._build_keyboard(reply_markup)
        data = await self._api_call(
            "PUT", "/messages",
            params={"message_id": str(message_id)},
            json_body=payload
        )
        if data is None:
            # Редактирование могло не удаться (например, сообщение старше 7 суток) — дублируем новым сообщением
            await self.send_message(user_id, text, reply_markup=reply_markup)

    # ---------- Обработка событий ----------

    async def handle_update(self, update: dict):
        """Обрабатывает входящие события (updates) от MAX API."""
        update_type = update.get("update_type")

        if update_type == "message_created":
            await self._handle_message_created(update)
        elif update_type == "message_callback":
            await self._handle_message_callback(update)
        elif update_type == "bot_started":
            sender = update.get("user") or {}
            user_id = str(sender.get("user_id", ""))
            if user_id:
                await self.user_service.update_username(user_id, sender.get("username"))
                await self.handle_start(user_id)
        # Прочие типы событий (bot_stopped, dialog_*) игнорируются

    def _extract_message(self, update: dict) -> Optional[dict]:
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        return message

    async def _handle_message_created(self, update: dict):
        message = self._extract_message(update)
        if message is None:
            return

        sender = message.get("sender") or {}
        user_id = str(sender.get("user_id", ""))

        # Текст может лежать в body.text (стандартный формат MAX)
        body = message.get("body") or {}
        text = (body.get("text") or "").strip()

        # Fallback: сообщение с контактом/кнопкой без текста — игнорируем
        if not user_id or not text:
            return

        # 1. Регистрация / обновление username
        await self.user_service.update_username(user_id, sender.get("username"))

        # 2. Маршрутизация команд
        if text.startswith("/"):
            if text.startswith("/start_request"):
                clean_text = text.lstrip("/")
                await self.beneficiary_handler.handle_message(user_id, clean_text)
            elif text.startswith("/start"):
                await self.handle_start(user_id)
            elif text.startswith("/help"):
                await self.handle_help(user_id)
            elif text.startswith("/admin_panel"):
                await self.handle_admin_panel(user_id)
            elif text.startswith("/list_users"):
                await self.handle_list_users(user_id)
            elif text.startswith("/get_id"):
                await self.handle_get_id(user_id, text)
            elif text.startswith(("/set_admin", "/remove_admin", "/set_volunteer", "/remove_volunteer")):
                await self.handle_role_command(user_id, text)
            elif text.startswith(("/take", "/complete", "/view_requests")):
                clean_text = text.lstrip("/")
                await self.volunteer_handler.handle_message(user_id, clean_text)
            else:
                # Кастомная команда (например /Продукты), передаем без слэша
                clean_text = text.lstrip("/")
                await self.beneficiary_handler.handle_message(user_id, clean_text)
                await self.volunteer_handler.handle_message(user_id, clean_text)
        else:
            # Обычный текст
            await self.beneficiary_handler.handle_message(user_id, text)
            await self.volunteer_handler.handle_message(user_id, text)

    async def _handle_message_callback(self, update: dict):
        """Обработка нажатий на inline-кнопки (type='callback')."""
        callback = update.get("callback") or {}
        callback_id = callback.get("callback_id")
        payload = str(callback.get("payload") or "")

        message = self._extract_message(update)
        sender = (message.get("sender") or {}) if message else (update.get("user") or {})
        user_id = str(sender.get("user_id", ""))
        if not user_id:
            return

        # 1. Регистрация / обновление username
        await self.user_service.update_username(user_id, sender.get("username"))

        try:
            await self.beneficiary_handler.handle_callback(user_id, payload)
            await self.volunteer_handler.handle_message(user_id, payload)
        finally:
            if callback_id:
                await self.answer_callback(callback_id)

    async def handle_start(self, user_id: str):
        role = await self.user_service.get_user_role(user_id)
        welcome_text = "<b>Здравствуйте!</b> Это волонтерский бот помощи (MAX Messenger).\n\n"
        if role == "beneficiary":
            welcome_text += "Если вам нужна помощь, отправьте: <code>/start_request</code>"
        elif role == "superadmin":
            welcome_text += "Вы вошли с правами <b>суперадминистратора (superadmin)</b>."
        elif role == "admin":
            welcome_text += "Вы вошли с правами <b>администратора (admin)</b>."
        elif role == "volunteer":
            welcome_text += "Вы зарегистрированы как <b>волонтер</b>."
        else:
            welcome_text += "Ваша роль пока не определена."
        
        welcome_text += "\n\nНапишите <code>/help</code>, чтобы увидеть доступные команды."
        await self.send_message(user_id, welcome_text)

    async def handle_help(self, user_id: str):
        role = await self.user_service.get_user_role(user_id)
        
        # Определяем команды по ролям
        commands = {
            "beneficiary": [("/start_request", "Создать заявку на помощь")],
            "volunteer": [
                ("/view_requests", "Список новых заявок"),
                ("/take <ID>", "Взять заявку"),
                ("/complete <ID>", "Завершить заявку")
            ],
            "admin": [
                ("/view_requests", "Список заявок"),
                ("/set_volunteer <ID>", "Назначить волонтера"),
                ("/remove_volunteer <ID>", "Удалить волонтера"),
                ("/list_users", "Список всех пользователей"),
                ("/get_id", "Узнать ID")
            ],
            "superadmin": [
                ("/set_admin <ID>", "Назначить админа"),
                ("/remove_admin <ID>", "Удалить админа"),
                ("/set_volunteer <ID>", "Назначить волонтера"),
                ("/remove_volunteer <ID>", "Удалить волонтера"),
                ("/list_users", "Список всех пользователей"),
                ("/get_id", "Узнать ID")
            ]
        }
        
        cmds = commands.get(role, [])
        if not cmds:
            await self.send_message(user_id, "Ваша роль не определена.")
            return

        help_text = f"<b>🔧 Доступные команды ({role}):</b>\n\n"
        for cmd, desc in cmds:
            help_text += f"🔹 <b>{cmd}</b> — {desc}\n"
        help_text += "\n<i>Нажмите на команду или скопируйте её, чтобы вставить в сообщение.</i>"
            
        mid = await self.send_message(user_id, help_text)
        # Пробуем закрепить сообщение
        await self.pin_message(mid)

    async def handle_admin_panel(self, user_id: str):
        user_role = await self.user_service.get_user_role(user_id)
        if self.user_service.get_role_power(user_role) >= 2:
            panel_text = "<b>🛡 Панель управления:</b>\n"
            panel_text += "• Отправьте <code>/set_volunteer &lt;ID&gt;</code> для назначения волонтера\n"
            panel_text += "• Отправьте <code>/remove_volunteer &lt;ID&gt;</code> для удаления волонтера\n"
            panel_text += "• Отправьте <code>/list_users</code> для просмотра пользователей\n"
            if user_role == "superadmin":
                panel_text += "• Отправьте <code>/set_admin &lt;ID&gt;</code> для назначения администратора\n"
                panel_text += "• Отправьте <code>/remove_admin &lt;ID&gt;</code> для удаления администратора\n"
            await self.send_message(user_id, panel_text)
        else:
            await self.send_message(user_id, "У вас нет прав.")

    async def handle_list_users(self, user_id: str):
        user_role = await self.user_service.get_user_role(user_id)
        if self.user_service.get_role_power(user_role) < 2:
            await self.send_message(user_id, "У вас нет прав.")
            return
        users = await self.user_service.list_users()
        response = "<b>Список пользователей:</b>\n"
        for user in users:
            response += f"• ID: <code>{user.platform_user_id}</code> | Роль: <b>{user.role}</b>\n"
        await self.send_message(user_id, response)

    async def handle_get_id(self, user_id: str, text: str):
        args = text.split()
        if len(args) == 2:
            username = args[1].lstrip("@")
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(UserDB).filter(UserDB.username == username))
                user = result.scalar_one_or_none()
                if user:
                    await self.send_message(user_id, f"ID пользователя @{username}: {user.platform_user_id}")
                else:
                    await self.send_message(user_id, f"Пользователь @{username} не найден.")
            return
        await self.send_message(user_id, f"Ваш ID: {user_id}")

    async def handle_role_command(self, user_id: str, text: str):
        parts = text.split()
        if len(parts) != 2:
            await self.send_message(user_id, "Использование: /command <user_id>")
            return
        cmd, target_id = parts[0], parts[1]

        role_map = {
            "/set_admin": "admin",
            "/remove_admin": "beneficiary",
            "/set_volunteer": "volunteer",
            "/remove_volunteer": "beneficiary"
        }

        if cmd in ["/set_admin", "/set_volunteer"]:
            new_role = role_map[cmd]
            success, msg = await self.user_service.set_user_role(target_id, new_role, user_id)
            await self.send_message(user_id, msg)
        elif cmd in ["/remove_admin", "/remove_volunteer"]:
            success, msg = await self.user_service.remove_role(target_id, user_id)
            await self.send_message(user_id, msg)

    async def set_bot_commands(self):
        """Регистрирует команды в платформе для отображения в меню '/' (используя поле 'name')."""
        commands = [
            {"name": "start", "description": "Запуск бота"},
            {"name": "help", "description": "Список всех команд"},
            {"name": "start_request", "description": "Создать заявку на помощь"},
            {"name": "view_requests", "description": "Список заявок"},
            {"name": "get_id", "description": "Узнать свой ID"}
        ]
        await self._api_call("PATCH", "/me/commands", json_body={"commands": commands})

    async def run(self):
        """Long-polling цикл получения updates от MAX API."""
        # Регистрируем команды при запуске бота
        await self.set_bot_commands()
        
        self.running = True
        logger.info("MaxBot started polling /updates...")
        while self.running:
            try:
                params = {"timeout": 30, "types": "message_created,message_callback,bot_started"}
                if self.marker is not None:
                    params["marker"] = self.marker

                response = await self.client.get(f"{self.base_url}/updates", params=params, timeout=35.0)
                if response.status_code == 200:
                    data = response.json()
                    self.marker = data.get("marker") or self.marker
                    for update in data.get("updates", []) or []:
                        try:
                            await self.handle_update(update)
                        except Exception:
                            logger.exception("Error handling update: %s", update)
                elif response.status_code == 401:
                    logger.error("Ошибка авторизации MAX API: проверьте BOT_TOKEN в .env")
                    await asyncio.sleep(10)
                else:
                    logger.warning("Unexpected /updates status %s", response.status_code)
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)

    async def stop(self):
        self.running = False
