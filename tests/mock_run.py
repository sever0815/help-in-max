import asyncio
from src.core.base_bot import BaseBot
from src.services.request_service import RequestService
from src.handlers.beneficiary import BeneficiaryHandler

class ConcreteBot(BaseBot):
    async def send_message(self, user_id: str, text: str, reply_markup=None):
        print(f"Bot [to {user_id}]: {text}")

    async def send_keyboard(self, user_id: str, text: str, options: list):
        print(f"Bot [to {user_id}]: {text} | Keyboard: {options}")

    async def on_message_received(self, user_id: str, text: str):
        pass

async def main():
    bot = ConcreteBot()
    request_service = RequestService()
    handler = BeneficiaryHandler(bot, request_service)
    
    user_id = "test_user"
    
    print("--- Simulating Beneficiary Flow ---")
    await handler.handle_message(user_id, "/help")
    await handler.handle_message(user_id, "Продукты")
    await handler.handle_message(user_id, "Нужен хлеб и молоко.")
    await handler.handle_message(user_id, "ул. Ленина, д. 1, кв. 1")
    
    # Verify request creation
    requests = await request_service.get_new_requests()
    print(f"\n--- Requests in DB: {len(requests)} ---")
    for r in requests:
        print(f"ID: {r.id}, Beneficiary: {r.beneficiary_id}, Category: {r.category}, Status: {r.status}")

if __name__ == "__main__":
    asyncio.run(main())
