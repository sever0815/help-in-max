# Используем официальный образ Python
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем пустой файл базы и даем права
RUN touch /app/bot_data.db && chmod 666 /app/bot_data.db

# Запускаем бота
CMD ["python", "main.py"]
