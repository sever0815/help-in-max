import httpx
import asyncio
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

async def test():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("Ошибка: BOT_TOKEN не найден в .env")
        return

    async with httpx.AsyncClient(verify=False) as client:
        # Пробуем отправить запрос на регистрацию команд
        url = "https://platform-api2.max.ru/set_my_commands"
        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }
        payload = {
            "commands": [
                {"command": "start", "description": "Запуск бота"},
                {"command": "help", "description": "Список команд"}
            ]
        }
        
        try:
            print(f"Отправляю запрос на {url}...")
            resp = await client.post(url, headers=headers, json=payload)
            print(f"Статус код: {resp.status_code}")
            print(f"Ответ: {resp.text}")
            
            if resp.status_code == 200:
                print("\nУСПЕХ: Метод /set_my_commands работает!")
            else:
                print("\nРЕЗУЛЬТАТ: Метод /set_my_commands вернул ошибку. Возможно, другой эндпоинт.")
                
        except Exception as e:
            print(f"Ошибка соединения: {e}")

if __name__ == "__main__":
    asyncio.run(test())
