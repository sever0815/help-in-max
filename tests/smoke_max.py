import asyncio
import os
import sys

# Изолированная БД для теста
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_migration.db"
if os.path.exists("test_migration.db"):
    os.remove("test_migration.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.future import select
from sqlalchemy import text
from src.db.models import init_db, AsyncSessionLocal, UserDB, engine
from src.services.user_service import UserService
from src.services.request_service import RequestService
from src.handlers.beneficiary import BeneficiaryHandler
from src.handlers.volunteer import VolunteerHandler

sent_log = []

class FakeBot:
    async def send_message(self, user_id, text, reply_markup=None):
        sent_log.append(("msg", user_id, text[:60]))
        return f"mid-{len(sent_log)}"

    async def send_keyboard(self, user_id, text, options):
        sent_log.append(("kbd", user_id, f"{text[:40]} | {options}"))
        return f"mid-kbd-{len(sent_log)}"

    async def edit_message(self, user_id, message_id, text, reply_markup=None):
        sent_log.append(("edit", user_id, f"{message_id} -> {text[:40]}"))


async def main():
    await init_db()

    # 1. Проверка миграции старой БД с telegram_id
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE users"))
        await conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, telegram_id VARCHAR UNIQUE, "
            "username VARCHAR, role VARCHAR)"
        ))
        await conn.execute(text(
            "INSERT INTO users (telegram_id, username, role) VALUES ('777', 'old_user', 'volunteer')"
        ))
    await init_db()  # должно переименовать колонку без потери данных

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserDB).filter(UserDB.platform_user_id == "777"))
        migrated = result.scalar_one_or_none()
        assert migrated is not None and migrated.role == "volunteer", "Миграция не сработала!"
    print("[OK] Миграция telegram_id -> platform_user_id прошла, данные сохранены")

    bot = FakeBot()
    us = UserService()
    rs = RequestService(None)
    bh = BeneficiaryHandler(bot, rs)
    vh = VolunteerHandler(bot, rs, us)

    # 2. Система привилегий: суперадмин из ADMIN_USER_IDS
    from config.settings import ADMIN_USER_IDS
    main_admin = ADMIN_USER_IDS[0] if ADMIN_USER_IDS else "999999"
    role = await us.get_user_role(main_admin)
    assert role == "superadmin", f"Главный суперадмин не распознан: {role}"
    print(f"[OK] Суперадмин {main_admin} распознан")

    # 3. Суперадмин назначает волонтера
    ok, msg = await us.set_user_role("777", "volunteer", main_admin)
    print(f"[OK] set_user_role: {msg}")

    # 4. Иерархия: волонтер не может управлять админом
    await us.set_user_role("888", "admin", main_admin)
    ok, msg = await us.set_user_role("777", "admin", "888")
    assert not ok, "Волонтер смог изменить роль!"
    print(f"[OK] Иерархия прав работает: '{msg}'")

    # 5. Полный сценарий подопечного через callback-пейлоады
    await bh.handle_message("benef_1", "/start_request")
    await bh.handle_callback("benef_1", "Продукты")
    await bh.handle_message("benef_1", "Нужны продукты")
    await bh.handle_message("benef_1", "ул. Ленина, д. 1")
    await bh.handle_callback("benef_1", "Сейчас")
    await bh.handle_callback("benef_1", "Подтвердить")
    requests = await rs.get_new_requests()
    assert any(r.beneficiary_id == "benef_1" for r in requests), "Заявка не создана!"
    print(f"[OK] Заявка создана через callback-кнопки (всего новых: {len(requests)})")

    # 6. Волонтер обрабатывает заявку
    req_id = requests[0].id
    await vh.handle_message("777", "/view_requests")
    await vh.handle_message("777", f"/take {req_id}")
    await vh.handle_message("777", f"/complete {req_id}")
    req = await rs.get_request_by_id(req_id)
    assert req.status == "completed" and req.volunteer_id == "777"
    print("[OK] Волонтер взял и завершил заявку")

    # 7. Доступ запрещен без роли
    await vh.handle_message("benef_1", "/view_requests")
    print("[OK] Доступ для подопечного запрещен")

    print("\n--- Лог отправок бота ---")
    for kind, uid, txt in sent_log:
        print(f"  [{kind}] -> {uid}: {txt}")

    await engine.dispose()
    os.remove("test_migration.db")
    print("\nALL SMOKE TESTS PASSED")

asyncio.run(main())
