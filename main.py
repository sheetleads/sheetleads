import os
import json
import time
import random
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright, TimeoutError

# --- НАСТРОЙКИ ---
# Укажи точное название твоей таблицы и листа
SPREADSHEET_NAME = "ТВОЯ_ТАБЛИЦА" 
WORKSHEET_NAME = "Лист1"

def get_gspread_client():
    """Авторизация в Google Sheets через переменную окружения."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("Переменная окружения GOOGLE_CREDENTIALS не найдена!")
    
    # Конвертируем строку из ENV в словарь
    creds_dict = json.loads(creds_json)
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(credentials)

def scrape_category(page, url):
    """Переходит по ссылке и парсит категорию бизнеса."""
    # Переходим по ссылке, ждем загрузки страницы (таймаут 30 сек)
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=10000)
    
    # Селектор для кнопки категории в Google Maps (обычно это кнопка с классом DkEaL)
    # Если Google изменит дизайн, этот селектор нужно будет обновить
    category_locator = page.locator('button.DkEaL').first
    
    # Ждем появления элемента максимум 5 секунд
    category_locator.wait_for(state="visible", timeout=5000)
    return category_locator.inner_text()

def main():
    print("Подключение к Google Sheets...")
    client = get_gspread_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    
    print("Получение данных из таблицы...")
    # Получаем все данные. Первая строка будет ключами словаря
    records = sheet.get_all_records()
    
    # Получаем заголовки (1-я строка), чтобы вычислить индексы колонок
    headers = sheet.row_values(1)
    
    if "Map Link" not in headers or "Category" not in headers:
        print("Ошибка: Колонки 'Map Link' или 'Category' не найдены!")
        return

    # gspread использует индексы с 1, поэтому +1
    category_col_index = headers.index("Category") + 1

    print("Запуск браузера...")
    with sync_playwright() as p:
        # Запускаем Chromium в headless-режиме
        browser = p.chromium.launch(headless=True)
        # Устанавливаем юзер-агент, чтобы быть похожими на реального пользователя
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Идем по строкам (со 2-й, так как 1-я - заголовки)
        for i, row in enumerate(records, start=2):
            map_link = row.get("Map Link", "").strip()
            category = str(row.get("Category", "")).strip()

            # Если есть ссылка, но категория пустая
            if map_link and not category:
                print(f"[Строка {i}] Обработка ссылки: {map_link}")
                
                try:
                    # Пытаемся получить категорию
                    result_category = scrape_category(page, map_link)
                    if not result_category:
                        result_category = "Not Found"
                except Exception as e:
                    # Жесткий перехват любых ошибок (таймауты, битые ссылки)
                    print(f"[Строка {i}] Ошибка парсинга: {type(e).__name__}")
                    result_category = "Not Found"

                # Мгновенная запись в Google Таблицу
                try:
                    sheet.update_cell(i, category_col_index, result_category)
                    print(f"[Строка {i}] Записано: {result_category}")
                except Exception as e:
                    print(f"[Строка {i}] Ошибка записи в таблицу: {e}")

                # Случайная задержка от 3 до 6 секунд для защиты от бана
                delay = random.randint(3, 6)
                print(f"Ожидание {delay} сек...")
                time.sleep(delay)

        print("Процесс завершен. Закрытие браузера.")
        browser.close()

if __name__ == "__main__":
    main()