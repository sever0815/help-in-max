import asyncio
import logging
import time
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
        self.user_states: Dict[str, Dict[str, Any]] = {}

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
        self._start_times: Dict[str, float] = {}  # Для отслеживания времени handle_start

    # ---------- Низкоуровневые вызовы API ----------

    async def _api_call(self, method: str, endpoint: str, *, params: Optional[dict] = None, json_body: Optional[dict] = None) -> Optional[dict]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = await self.client.request(method, url, params=params, json=json_body)
            if response.status_code != 200:
                logger.error(f"API error on {method} {endpoint}: status={response.status_code}, body={response.text}")
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
        """Отправляет текстовое сообщение пользователю через MAX API.
        К кнопке /help добавляется в конец клавиатуры автоматически.
        """
        help_row = [{"type": "callback", "text": "Помощь", "payload": "/help"}]
        if reply_markup is not None:
            if isinstance(reply_markup, list):
                reply_markup = reply_markup + [help_row]
            else:
                reply_markup = [reply_markup, help_row]
        else:
            reply_markup = [help_row]
        payload: Dict[str, Any] = {"text": text, "format": "html"}
        payload["attachments"] = self._build_keyboard(reply_markup)
        data = await self._api_call(
            "POST", "/messages",
            params={"user_id": user_id},
            json_body=payload
        )
        if data is None:
            logger.error(f"Failed to send message to {user_id}")
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

    async def answer_callback(self, callback_id: str, text: str = "", attachments: Optional[list] = None) -> None:
        """Подтверждает нажатие кнопки и обновляет сообщение, сохраняя кнопки."""
        body: Dict[str, Any] = {"message": {"text": text}}
        if attachments:
            body["message"]["attachments"] = attachments
        await self._api_call("POST", "/answers", params={"callback_id": callback_id}, json_body=body)

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
        logger.info(f"Получен update: {update}")
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

        # Проверка блокировки — заблокированные пользователи полностью игнорируются
        user_role = await self.user_service.get_user_role(user_id)
        if user_role == "blocked":
            return

        # 1. Регистрация / обновление username
        await self.user_service.update_username(user_id, sender.get("username"))

        # 2. Проверка ожидания ID для роли
        state_data = self.user_states.get(user_id)
        if state_data and state_data.get("pending_role_command"):
            cmd = state_data["pending_role_command"]
            target_id = text.strip()
            role_map = {
                "/set_admin": "admin",
                "/remove_admin": "beneficiary",
                "/set_volunteer": "volunteer",
                "/remove_volunteer": "beneficiary"
            }
            new_role = role_map[cmd]
            success, msg = await self.user_service.set_user_role(target_id, new_role, user_id)
            await self.send_message(user_id, msg)
            self.user_states.pop(user_id, None)
            return

        # 3. Маршрутизация команд
        if text.startswith("/"):
            if text.startswith("/start_request"):
                # Регистрируем пользователя как beneficiary, если он ещё не в базе
                await self.user_service.update_username(user_id, sender.get("username"))
                await self.beneficiary_handler.handle_message(user_id, text)
            elif text.startswith("/start"):
                last_start = self._start_times.get(user_id, 0)
                if time.time() - last_start > 5:
                    await self.handle_start(user_id)
            elif text.startswith("/help"):
                await self.handle_help(user_id)
            elif text.startswith("/admin_panel"):
                await self.handle_admin_panel(user_id)
            elif text.startswith("/list_users"):
                await self.handle_list_users(user_id)
            elif text.startswith("/get_id"):
                await self.handle_get_id(user_id, text)
            elif text.startswith(("/set_admin", "/remove_admin", "/set_volunteer", "/remove_volunteer", "/block", "/unblock")):
                await self.handle_role_command(user_id, text)
            elif text.startswith("/set_name"):
                await self.handle_set_name(user_id, text)
            elif text.startswith(("/take", "/complete", "/view_requests")):
                await self.volunteer_handler.handle_message(user_id, text)
            else:
                # Кастомная команда (например /Продукты), передаем без слэша
                clean_text = text.lstrip("/")
                await self.beneficiary_handler.handle_message(user_id, clean_text)
        else:
            # Обычный текст — только beneficiary
            try:
                await self.beneficiary_handler.handle_message(user_id, text)
            except Exception as e:
                logger.exception(f"Error in beneficiary_handler: {e}")

    async def _handle_message_callback(self, update: dict):
        """Обработка нажатий на inline-кнопки (type='callback')."""
        callback = update.get("callback") or {}
        callback_id = callback.get("callback_id") or callback.get("id")
        payload = str(callback.get("payload") or "")
        # Для message_callback user_id берётся из callback.user.user_id
        callback_user = callback.get("user") or {}
        user_id = str(callback_user.get("user_id", ""))
        if not user_id:
            return

        # Проверка блокировки — заблокированные пользователи полностью игнорируются
        user_role = await self.user_service.get_user_role(user_id)
        if user_role == "blocked":
            return

        # 1. Регистрация / обновление username
        # Извлекаем данные из оригинального сообщения для обновления (чтобы кнопки не исчезли)
        original_message = update.get("message") or {}
        message_text = original_message.get("body", {}).get("text", "")
        message_attachments = original_message.get("attachments") or []

        await self.user_service.update_username(user_id, callback_user.get("username"))

        try:
            # Обработка кнопок заявок (view_request, accept_request, reject_request, complete_request)
            if payload.startswith("view_request:"):
                request_id = int(payload.split(":", 1)[1])
                request = await self.request_service.get_request_by_id(request_id)
                if request:
                    from src.db.models import AsyncSessionLocal, UserDB
                    from sqlalchemy.future import select
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(UserDB).filter(UserDB.platform_user_id == str(request.beneficiary_id))
                        )
                        user = result.scalar_one_or_none()
                        user_name = user.full_name if user and user.full_name else "—"

                    status_map = {"new": "Ожидает", "accepted": "Принята", "completed": "Завершена", "cancelled": "Отменена"}
                    category_map = {"products": "Продукты", "walk": "Прогулка", "cleaning": "Уборка", "other": "Другое"}
                    status_text = status_map.get(request.status, request.status)
                    category_text = category_map.get(request.category, request.category)
                    full_info = (f"📋 <b>Заявка #{request.id}</b>\n\n"
                                 f"👕 Категория: {category_text}\n"
                                 f"📍 Адрес: {request.address}\n"
                                 f"🕐 Время: {request.scheduled_time}\n"
                                 f"📞 Телефон: {request.phone or '—'}\n"
                                 f"📝 Детали: {request.description or '—'}\n"
                                 f"👤 ФИО: {user_name}\n"
                                 f"📊 Статус: {status_text}")
                    keyboard = [
                        [{"type": "callback", "text": "Принять", "payload": f"accept_request:{request.id}"}],
                        [{"type": "callback", "text": "Отклонить", "payload": f"reject_request:{request.id}"}]
                    ]
                    await self.send_message(user_id, full_info, reply_markup=keyboard)
                else:
                    await self.send_message(user_id, "Заявка не найдена.")
            elif payload.startswith("accept_request:"):
                request_id = int(payload.split(":", 1)[1])
                request = await self.request_service.accept_request(request_id, user_id)
                if request:
                    from src.db.models import AsyncSessionLocal, UserDB
                    from sqlalchemy.future import select
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(UserDB).filter(UserDB.platform_user_id == str(request.beneficiary_id))
                        )
                        user = result.scalar_one_or_none()
                        user_name = user.full_name if user and user.full_name else "—"

                    status_map = {"new": "Ожидает", "accepted": "Принята", "completed": "Завершена", "cancelled": "Отменена"}
                    category_map = {"products": "Продукты", "walk": "Прогулка", "cleaning": "Уборка", "other": "Другое"}
                    status_text = status_map.get(request.status, request.status)
                    category_text = category_map.get(request.category, request.category)
                    full_info = (f"📋 <b>Заявка #{request.id}</b>\n\n"
                                 f"👕 Категория: {category_text}\n"
                                 f"📍 Адрес: {request.address}\n"
                                 f"🕐 Время: {request.scheduled_time}\n"
                                 f"📞 Телефон: {request.phone or '—'}\n"
                                 f"📝 Детали: {request.description or '—'}\n"
                                 f"👤 ФИО: {user_name}\n"
                                 f"📊 Статус: {status_text}")
                    keyboard = [
                        [{"type": "callback", "text": "Завершить", "payload": f"complete_request:{request.id}"}],
                        [{"type": "callback", "text": "Отклонить", "payload": f"reject_request:{request.id}"}]
                    ]
                    await self.send_message(user_id, full_info, reply_markup=keyboard)
                else:
                    await self.send_message(user_id, "Не удалось принять заявку. Возможно, она уже принята или не существует.")
            elif payload.startswith("reject_request:"):
                request_id = int(payload.split(":", 1)[1])
                request = await self.request_service.reject_request(request_id)
                if request:
                    await self.send_message(user_id, f"Заявка #{request_id} отклонена и возвращена в список доступных.")
                else:
                    await self.send_message(user_id, "Не удалось отклонить заявку.")
            elif payload.startswith("complete_request:"):
                request_id = int(payload.split(":", 1)[1])
                request = await self.request_service.complete_request(request_id)
                if request:
                    await self.send_message(user_id, f"Заявка #{request_id} завершена.")
                else:
                    await self.send_message(user_id, "Не удалось завершить заявку.")
            elif payload.startswith("cancel_request:"):
                # Отмена заявки пользователем
                request_id = int(payload.split(":", 1)[1])
                request = await self.request_service.cancel_request(request_id)
                if request:
                    await self.send_message(user_id, f"Заявка #{request_id} отменена.")
                else:
                    await self.send_message(user_id, "Не удалось отменить заявку.")
            elif payload.startswith("copy_id:"):
                id_to_copy = payload.split(":", 1)[1]
                await self.send_message(user_id, f"ID: {id_to_copy}")
            elif payload == "/my_requests":
                await self.handle_my_requests(user_id)
            elif payload == "/active_request":
                await self.handle_active_request(user_id)
            # Если нажата кнопка с командой (например /start_request или /view_requests)
            elif payload.startswith("/"):
                if payload.startswith("/start_request"):
                    await self.beneficiary_handler.handle_message(user_id, payload)
                elif payload.startswith(("/take", "/complete", "/view_requests")):
                    await self.volunteer_handler.handle_message(user_id, payload)
                elif payload == "/start":
                    await self.handle_start(user_id)
                elif payload == "/help":
                    await self.handle_help(user_id)
                elif payload == "/list_users":
                    await self.handle_list_users(user_id)
                elif payload == "/get_id":
                    await self.handle_get_id(user_id, payload)
                elif payload.startswith(("/set_admin", "/remove_admin", "/set_volunteer", "/remove_volunteer")):
                    await self.handle_role_command(user_id, payload)
                elif payload.startswith("/set_name"):
                    await self.handle_set_name(user_id, payload)
                else:
                    await self.beneficiary_handler.handle_message(user_id, payload.lstrip("/"))
            else:
                await self.beneficiary_handler.handle_callback(user_id, payload)
        except Exception:
            logger.exception("Error handling callback payload: %s", payload)
        finally:
            if callback_id:
                try:
                    await self.answer_callback(callback_id, text=message_text, attachments=message_attachments)
                except Exception:
                    pass

    async def handle_start(self, user_id: str):
        self._start_times[user_id] = time.time()
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
        keyboard_rows = []
        if role == "beneficiary":
            keyboard_rows.append([{"type": "callback", "text": "Создать заявку", "payload": "/start_request"}])
        await self.send_message(user_id, welcome_text, reply_markup=keyboard_rows)

    async def handle_help(self, user_id: str):
        role = await self.user_service.get_user_role(user_id)

        # Определяем команды по ролям: (payload, описание, текст кнопки)
        commands = {
            "beneficiary": [
                ("/start_request", "Создать заявку на помощь", "Создать заявку"),
                ("/my_requests", "Мои заявки", "Мои заявки")
            ],
            "volunteer": [
                ("/view_requests", "Список новых заявок", "Список заявок"),
                ("/take <ID>", "Взять заявку", "Взять заявку"),
                ("/complete <ID>", "Завершить заявку", "Завершить заявку")
            ],
            "admin": [
                ("/view_requests", "Список заявок", "Список заявок"),
                ("/set_volunteer <ID>", "Назначить волонтера", "Назначить волонтера"),
                ("/remove_volunteer <ID>", "Удалить волонтера", "Удалить волонтера"),
                ("/set_name <ID> <ФИО>", "Добавить ФИО пользователя", "Добавить ФИО"),
                ("/block <ID>", "Заблокировать пользователя", "Заблокировать"),
                ("/unblock <ID>", "Разблокировать пользователя", "Разблокировать"),
                ("/list_users", "Список всех пользователей", "Список пользователей"),
                ("/get_id", "Узнать ID", "Узнать ID")
            ],
            "superadmin": [
                ("/set_admin <ID>", "Назначить админа", "Назначить админа"),
                ("/remove_admin <ID>", "Удалить админа", "Удалить админа"),
                ("/set_volunteer <ID>", "Назначить волонтера", "Назначить волонтера"),
                ("/remove_volunteer <ID>", "Удалить волонтера", "Удалить волонтера"),
                ("/set_name <ID> <ФИО>", "Добавить ФИО пользователя", "Добавить ФИО"),
                ("/block <ID>", "Заблокировать пользователя", "Заблокировать"),
                ("/unblock <ID>", "Разблокировать пользователя", "Разблокировать"),
                ("/list_users", "Список всех пользователей", "Список пользователей"),
                ("/get_id", "Узнать ID", "Узнать ID")
            ]
        }
        
        cmds = commands.get(role, [])
        if not cmds:
            await self.send_message(user_id, "Ваша роль не определена.")
            return

        help_text = f"<b>🔧 Доступные команды ({role}):</b>\n\n"

        # Формируем список инлайн-кнопок для быстрого вызова
        keyboard_rows = []
        for cmd, desc, btn_text in cmds:
            help_text += f"🔹 <b>{cmd}</b> — {desc}\n"
            # Payload — только команда без аргументов, чтобы бот запросил ID
            payload = cmd.split()[0]
            keyboard_rows.append([{"type": "callback", "text": btn_text, "payload": payload}])
            
        help_text += "\n<i>Нажмите на кнопку ниже для быстрого вызова команды.</i>"
            
        await self.send_message(user_id, help_text, reply_markup=keyboard_rows)

    async def handle_active_request(self, user_id: str):
        """Показать активную заявку волонтёра с кнопкой завершения."""
        from src.db.models import AsyncSessionLocal, UserDB
        from sqlalchemy.future import select
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(
                    RequestDB.volunteer_id == str(user_id),
                    RequestDB.status == "accepted"
                )
            )
            request = result.scalar_one_or_none()

        if not request:
            await self.send_message(user_id, "У вас нет активных заявок.")
            return

        # Получаем ФИО пользователя
        from src.db.models import AsyncSessionLocal, UserDB
        from sqlalchemy.future import select
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserDB).filter(UserDB.platform_user_id == str(request.beneficiary_id))
            )
            user = result.scalar_one_or_none()
            user_name = user.full_name if user and user.full_name else "—"

        category_map = {"products": "Продукты", "walk": "Прогулка", "cleaning": "Уборка", "other": "Другое"}
        category_text = category_map.get(request.category, request.category)
        full_info = (f"📋 <b>Ваша активная заявка #{request.id}</b>\n\n"
                     f"👕 Категория: {category_text}\n"
                     f"📍 Адрес: {request.address}\n"
                     f"🕐 Время: {request.scheduled_time}\n"
                     f"📞 Телефон: {request.phone or '—'}\n"
                     f"📝 Детали: {request.description or '—'}\n"
                     f"👤 ФИО: {user_name}\n"
                     f"📊 Статус: Принята вами")

        keyboard = [
            [{"type": "callback", "text": "Завершить", "payload": f"complete_request:{request.id}"}]
        ]
        await self.send_message(user_id, full_info, reply_markup=keyboard)

    async def handle_my_requests(self, user_id: str):
        """Показать активные заявки пользователя с кнопкой отмены."""
        requests = await self.request_service.get_user_requests(user_id)
        # Фильтруем — показываем только активные заявки (не завершённые и не отменённые)
        active_requests = [r for r in requests if r.status in ("new", "accepted")]
        if not active_requests:
            await self.send_message(user_id, "У вас нет активных заявок.")
            return

        for req in active_requests:
            # Получаем ФИО волонтёра, если заявка принята
            volunteer_name = "—"
            if req.volunteer_id:
                from src.db.models import AsyncSessionLocal, UserDB
                from sqlalchemy.future import select
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(UserDB).filter(UserDB.platform_user_id == str(req.volunteer_id))
                    )
                    volunteer = result.scalar_one_or_none()
                    if volunteer and volunteer.full_name:
                        volunteer_name = volunteer.full_name

            status_map = {
                "new": "Ожидает",
                "accepted": f"Принята: {volunteer_name}",
                "completed": "Завершена",
                "cancelled": "Отменена"
            }
            category_map = {"products": "Продукты", "walk": "Прогулка", "cleaning": "Уборка", "other": "Другое"}
            status_text = status_map.get(req.status, req.status)
            category_text = category_map.get(req.category, req.category)

            request_info = (f"📋 <b>Заявка #{req.id}</b>\n\n"
                           f"👕 Категория: {category_text}\n"
                           f"📍 Адрес: {req.address}\n"
                           f"🕐 Время: {req.scheduled_time}\n"
                           f"📞 Телефон: {req.phone or '—'}\n"
                           f"📝 Детали: {req.description or '—'}\n"
                           f"📊 Статус: {status_text}")

            # Кнопка отмены только для активных заявок
            if req.status in ("new", "accepted"):
                keyboard = [
                    [{"type": "callback", "text": "Отклонить", "payload": f"cancel_request:{req.id}"}]
                ]
                await self.send_message(user_id, request_info, reply_markup=keyboard)
            else:
                await self.send_message(user_id, request_info)

    async def handle_admin_panel(self, user_id: str):
        user_role = await self.user_service.get_user_role(user_id)
        if self.user_service.get_role_power(user_role) >= 2:
            panel_text = "<b>🛡 Панель управления:</b>\n"
            panel_text += "• Отправьте <code>/set_volunteer &lt;ID&gt;</code> для назначения волонтера\n"
            panel_text += "• Отправьте <code>/remove_volunteer &lt;ID&gt;</code> для удаления волонтера\n"
            panel_text += "• Отправьте <code>/set_name &lt;ID&gt; &lt;ФИО&gt;</code> для добавления ФИО пользователя\n"
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

        # Группировка по категориям
        categories = {
            "Администраторы": [],
            "Волонтёры": [],
            "Подопечные": []
        }
        for user in users:
            if user.role in ("admin", "superadmin"):
                categories["Администраторы"].append(user)
            elif user.role == "volunteer":
                categories["Волонтёры"].append(user)
            else:
                categories["Подопечные"].append(user)

        # Сортировка по ФИО (если есть), затем по ID
        def sort_key(u):
            return (u.full_name or "", u.platform_user_id)

        response = "<b>📋 Список пользователей:</b>\n\n"
        keyboard_rows = []
        for cat_name, cat_users in categories.items():
            if not cat_users:
                continue
            cat_users.sort(key=sort_key)
            response += f"<b>{cat_name}:</b>\n"
            for user in cat_users:
                name_str = f" | ФИО: {user.full_name}" if user.full_name else ""
                response += f"  • {user.platform_user_id}{name_str}\n"
                # Кнопка с ID — при нажатии бот отправит ID сообщением для копирования
                keyboard_rows.append([{"type": "callback", "text": f"📋 {user.platform_user_id}", "payload": f"copy_id:{user.platform_user_id}"}])
            response += "\n"
        await self.send_message(user_id, response, reply_markup=keyboard_rows)

    async def handle_set_name(self, user_id: str, text: str):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await self.send_message(user_id, "Использование: /set_name <ID> <ФИО>\n\nПример: /set_name 387041392 Иванов Иван Иванович")
            return
        _, target_id, full_name = parts
        success, msg = await self.user_service.set_user_name(target_id, full_name, user_id)
        await self.send_message(user_id, msg)

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
        cmd = parts[0]
        valid_cmds = {"/set_admin", "/remove_admin", "/set_volunteer", "/remove_volunteer", "/block", "/unblock"}
        if cmd not in valid_cmds:
            await self.send_message(user_id, "Неизвестная команда.")
            return

        if len(parts) == 1:
            # Сохраняем ожидание ID
            self.user_states[user_id] = {"pending_role_command": cmd}
            await self.send_message(user_id, f"Введите ID пользователя для {cmd}:")
            return

        if len(parts) >= 2:
            target_id = parts[1]
            role_map = {
                "/set_admin": "admin",
                "/remove_admin": "beneficiary",
                "/set_volunteer": "volunteer",
                "/remove_volunteer": "beneficiary",
                "/block": "blocked",
                "/unblock": "beneficiary"
            }
            new_role = role_map[cmd]
            success, msg = await self.user_service.set_user_role(target_id, new_role, user_id)
            await self.send_message(user_id, msg)
            # Убираем pending state, если был
            if user_id in self.user_states:
                self.user_states.pop(user_id)

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
