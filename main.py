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
    """Парсинг категории бизнеса через Playwright с обходом защиты Google."""
    try:
        # domcontentloaded вместо networkidle, так как карты грузятся бесконечно
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        
        # Даем JS скриптам карт время на рендер интерфейса
        page.wait_for_timeout(3000)
        
        # 1. Попытка убить всплывающее окно Cookies (если оно появилось)
        try:
            cookie_btn = page.locator('button:has-text("Accept all"), button:has-text("Принять все"), button:has-text("Reject all")').first
            if cookie_btn.is_visible(timeout=2000):
                cookie_btn.click()
                page.wait_for_timeout(1500)
        except Exception:
            pass # Окна нет, идем дальше
        
        # 2. Несколько вариантов селекторов (Google часто меняет классы)
        selectors = [
            'button.DkEaL',  # Самый частый класс категории
            'button[jsaction*="pane.rating.category"]', # Альтернативный
            '.fontBodyMedium' # Широкий поиск по стилю текста
        ]
        
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                # Ждем появления элемента максимум 4 секунды
                locator.wait_for(state="visible", timeout=4000)
                
                category_text = locator.inner_text().strip()
                if category_text and len(category_text) > 2:
                    # Убираем точку, которую Google иногда ставит перед текстом
                    return category_text.replace("·", "").strip()
            except Exception:
                continue
                
        logger.warning(f"Не найдены селекторы для: {url}")
        return "Not Found"
        
    except Exception as e:
        logger.warning(f"Ошибка загрузки или таймаут {url}: {str(e)}")
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
        # Флаги для предотвращения зависаний (OOM) внутри Docker-контейнера
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--mute-audio"
            ]
        )
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for i, row in enumerate(data[1:], start=2):
            current_category = row[cat_idx] if len(row) > cat_idx else ""
            map_url = row[map_idx] if len(row) > map_idx else ""

            if map_url and not current_category:
                logger.info(f"Обработка строки {i}: {map_url}")
                
                category_result = scrape_category(page, map_url)
                
                # Мгновенное обновление ячейки
                sheet.update_cell(i, cat_idx + 1, category_result)
                logger.info(f"Результат: {category_result}")

                # Случайная задержка для имитации действий человека
                wait_time = random.randint(3, 6)
                time.sleep(wait_time)
            else:
                pass # Пропускаем заполненные или пустые строки без лишнего спама в логи

        browser.close()
    logger.info("Работа завершена!")

if __name__ == "__main__":
    main()
