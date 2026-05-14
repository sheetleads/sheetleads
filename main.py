import os
import json
import time
import random
import logging
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Чтение настроек из переменных окружения
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME")
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "Parsed_Leads")

def get_gspread_client():
    """Авторизация в Google Sheets через JSON из переменной окружения."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("Переменная GOOGLE_CREDENTIALS не установлена!")
    
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(credentials)

def scrape_category(page, url):
    """Парсинг категории бизнеса через Playwright."""
    try:
        # Увеличиваем таймаут для медленных прокси/сетей
        page.goto(url, timeout=60000, wait_until="networkidle")
        
        # Google Maps часто меняет классы, поэтому используем более общий селектор
        # Обычно категория — это кнопка рядом с рейтингом
        selector = 'button[jsaction*="pane.rating.category"]'
        
        # Ждем появления элемента
        page.wait_for_selector(selector, timeout=10000)
        category = page.locator(selector).first.inner_text()
        return category.strip()
    except Exception as e:
        logger.warning(f"Не удалось спарсить {url}: {str(e)}")
        return "Not Found"

def main():
    if not SPREADSHEET_NAME:
        logger.error("SPREADSHEET_NAME не задана!")
        return

    logger.info(f"Запуск скрипта для таблицы: {SPREADSHEET_NAME}")
    
    client = get_gspread_client()
    try:
        spreadsheet = client.open(SPREADSHEET_NAME)
        sheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except Exception as e:
        logger.error(f"Ошибка доступа к таблице: {e}")
        return

    # Получаем все данные одним запросом для экономии лимитов API
    data = sheet.get_all_values()
    if not data:
        logger.info("Таблица пуста.")
        return

    headers = data[0]
    try:
        map_idx = headers.index("Map Link")
        cat_idx = headers.index("Category")
    except ValueError:
        logger.error("Убедитесь, что в таблице есть колонки 'Map Link' и 'Category'!")
        return

    logger.info("Инициализация браузера...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Эмулируем реальный браузер
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Проходим по строкам (пропуская заголовок)
        for i, row in enumerate(data[1:], start=2):
            # Проверка, не заполнена ли уже категория
            current_category = row[cat_idx] if len(row) > cat_idx else ""
            map_url = row[map_idx] if len(row) > map_idx else ""

            if map_url and not current_category:
                logger.info(f"Обработка строки {i}: {map_url}")
                
                category_result = scrape_category(page, map_url)
                
                # Мгновенное обновление ячейки (индексы в gspread с 1)
                sheet.update_cell(i, cat_idx + 1, category_result)
                logger.info(f"Результат: {category_result}")

                # Анти-фрод задержка
                wait_time = random.randint(3, 6)
                time.sleep(wait_time)
            else:
                logger.info(f"Строка {i} пропущена (уже заполнена или нет ссылки)")

        browser.close()
    logger.info("Работа завершена!")

if __name__ == "__main__":
    main()
