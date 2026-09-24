import asyncio
from src.core.base_bot import BaseBot
from src.services.request_service import RequestService
from src.services.user_service import UserService
from src.handlers.beneficiary import BeneficiaryHandler
from src.handlers.volunteer import VolunteerHandler
from src.db.models import init_db, AsyncSessionLocal

class ConcreteBot(BaseBot):
    async def send_message(self, user_id: str, text: str, reply_markup=None):
        print(f"Bot [to {user_id}]: {text}")

    async def send_keyboard(self, user_id: str, text: str, options: list):
        print(f"Bot [to {user_id}]: {text} | Keyboard: {options}")
        return 1

    async def edit_message(self, user_id: str, message_id: int, text: str, reply_markup=None):
        print(f"Bot [edit {message_id} to {user_id}]: {text}")

    async def on_message_received(self, user_id: str, text: str):
        pass

async def main():
    await init_db()
    bot = ConcreteBot()
    request_service = RequestService(bot.notification_service if hasattr(bot, 'notification_service') else None)
    user_service = UserService()
    beneficiary_handler = BeneficiaryHandler(bot, request_service)
    volunteer_handler = VolunteerHandler(bot, request_service, user_service)
    
    beneficiary_id = "beneficiary_1"
    volunteer_id = "volunteer_1"
    
    print("--- Simulating Beneficiary Flow ---")
    await beneficiary_handler.handle_message(beneficiary_id, "/help")
    await beneficiary_handler.handle_message(beneficiary_id, "Продукты")
    await beneficiary_handler.handle_message(beneficiary_id, "Нужен хлеб и молоко.")
    await beneficiary_handler.handle_message(beneficiary_id, "ул. Ленина, д. 1, кв. 1")
    
    print("\n--- Simulating Volunteer Flow ---")
    async with AsyncSessionLocal() as session:
        from src.db.models import UserDB
        from sqlalchemy.future import select
        result = await session.execute(select(UserDB).filter(UserDB.platform_user_id == volunteer_id))
        user = result.scalar_one_or_none()
        if user:
            user.role = "volunteer"
        else:
            session.add(UserDB(platform_user_id=volunteer_id, role="volunteer"))
        await session.commit()
    
    requests = await request_service.get_new_requests()
    req_id = requests[0].id if requests else 1

    await volunteer_handler.handle_message(volunteer_id, "/view_requests")
    await volunteer_handler.handle_message(volunteer_id, f"/take {req_id}")
    await volunteer_handler.handle_message(volunteer_id, f"/complete {req_id}")
    
    # Verify final state
    request = await request_service.get_request_by_id(req_id)
    print(f"\n--- Final Request State ---")
    print(f"ID: {request.id}, Status: {request.status}, Volunteer: {request.volunteer_id}")

if __name__ == "__main__":
    asyncio.run(main())
