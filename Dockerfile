# Используем легковесный официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Обновляем pip и устанавливаем Python-библиотеки
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Устанавливаем Playwright с зависимостями для Chromium
# Эта команда ставит сам браузер и все нужные системные пакеты (шрифты, либы)
RUN playwright install --with-deps chromium

# Копируем весь остальной код в контейнер
COPY . .

# Команда, которая будет выполняться при старте контейнера
CMD ["python", "main.py"]