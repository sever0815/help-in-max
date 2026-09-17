import asyncio
from src.core.base_bot import BaseBot
from src.services.request_service import RequestService
from src.handlers.beneficiary import BeneficiaryHandler
from src.handlers.volunteer import VolunteerHandler
from src.db.models import init_db

class ConcreteBot(BaseBot):
    async def send_message(self, user_id: str, text: str, reply_markup=None):
        print(f"Bot [to {user_id}]: {text}")

    async def send_keyboard(self, user_id: str, text: str, options: list):
        print(f"Bot [to {user_id}]: {text} | Keyboard: {options}")

    async def on_message_received(self, user_id: str, text: str):
        pass

async def main():
    await init_db()
    bot = ConcreteBot()
    request_service = RequestService()
    beneficiary_handler = BeneficiaryHandler(bot, request_service)
    volunteer_handler = VolunteerHandler(bot, request_service)
    
    beneficiary_id = "beneficiary_1"
    volunteer_id = "volunteer_1"
    
    print("--- Simulating Beneficiary Flow ---")
    await beneficiary_handler.handle_message(beneficiary_id, "/help")
    await beneficiary_handler.handle_message(beneficiary_id, "Продукты")
    await beneficiary_handler.handle_message(beneficiary_id, "Нужен хлеб и молоко.")
    await beneficiary_handler.handle_message(beneficiary_id, "ул. Ленина, д. 1, кв. 1")
    
    print("\n--- Simulating Volunteer Flow ---")
    await volunteer_handler.handle_message(volunteer_id, "/view_requests")
    await volunteer_handler.handle_message(volunteer_id, "/take 1")
    await volunteer_handler.handle_message(volunteer_id, "/complete 1")
    
    # Verify final state
    request = await request_service.get_request_by_id(1)
    print(f"\n--- Final Request State ---")
    print(f"ID: {request.id}, Status: {request.status}, Volunteer: {request.volunteer_id}")

if __name__ == "__main__":
    asyncio.run(main())
