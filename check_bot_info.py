import asyncio
import httpx
from config.settings import BOT_TOKEN

async def check(auth_header: str, label: str):
    url = "https://platform-api2.max.ru/me"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
        try:
            response = await client.get(url, headers=headers)
            print(f"[{label}] Код: {response.status_code}, Ответ: {response.text}")
            return response.status_code == 200
        except Exception as e:
            print(f"[{label}] Ошибка соединения: {e}")
            return False

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "default_token_for_testing":
        print("Внимание: BOT_TOKEN не задан или имеет значение по умолчанию в файле .env!")
        return

    print(f"Проверяем токен: {BOT_TOKEN[:6]}***...")
    
    # 1. Проверяем напрямую токен
    ok = await check(BOT_TOKEN, "Формат: токен без префикса")
    if not ok:
        # 2. Проверяем с префиксом Bearer
        await check(f"Bearer {BOT_TOKEN}", "Формат: Bearer токен")

if __name__ == "__main__":
    asyncio.run(main())
