import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def debug():
    token = os.getenv("BOT_TOKEN")
    async with httpx.AsyncClient(verify=False) as client:
        url = "https://platform-api2.max.ru/me/commands"
        headers = {"Authorization": token, "Content-Type": "application/json"}
        
        variants = [
            [{"command": "start", "description": "Запуск"}],
            {"commands": [{"name": "start", "description": "Запуск"}]},
            {"commands": [{"command": "start", "text": "Запуск"}]}
        ]
        
        for i, payload in enumerate(variants):
            resp = await client.patch(url, headers=headers, json=payload)
            print(f"Вариант {i+1} -> Статус: {resp.status_code}, Ответ: {resp.text}")

if __name__ == "__main__":
    asyncio.run(debug())
