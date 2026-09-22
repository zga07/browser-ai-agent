import os
import time
from playwright.sync_api import sync_playwright, Page, BrowserContext

class BrowserEngine:
    def __init__(self, user_data_dir: str = "./browser_profile"):
        """
        Инициализирует Chromium с сохранением сессии (куки, логины).
        """
        self.user_data_dir = os.path.abspath(user_data_dir)
        self.playwright = sync_playwright().start()

        # Запускаем persistent context (не headless, чтобы видеть действия агента)
        self.context: BrowserContext = self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )

        # Берем уже открытую вкладку или создаем новую
        self.page: Page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def navigate_to_url(self, url: str) -> str:
        """Переходит по указанному URL."""
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return f"Successfully navigated to {url}"
        except Exception as e:
            return f"Error navigating to {url}: {str(e)}"

    def click_element(self, selector: str) -> str:
        """Кликает по элементу по селектору с базовой обработкой ошибок."""
        try:
            # Ожидаем появление элемента перед кликом
            self.page.wait_for_selector(selector, state="visible", timeout=7000)
            self.page.click(selector)
            return f"Successfully clicked: {selector}"
        except Exception as e:
            return f"Failed to click '{selector}'. Reason: {str(e)}"

    def type_text(self, selector: str, text: str) -> str:
        """Вводит текст в поле."""
        try:
            self.page.wait_for_selector(selector, state="visible", timeout=7000)
            self.page.fill(selector, text)
            return f"Successfully typed '{text}' into {selector}"
        except Exception as e:
            return f"Failed to type into '{selector}'. Reason: {str(e)}"

    def wait(self, seconds: int) -> str:
        """Делает паузу (нужна для ожидания динамического контента)."""
        time.sleep(seconds)
        return f"Waited for {seconds} seconds"

    def take_screenshot(self, filename: str = "screenshot.png") -> str:
        """Делает скриншот текущей страницы."""
        try:
            self.page.screenshot(path=filename)
            return f"Screenshot saved as {filename}"
        except Exception as e:
            return f"Failed to take screenshot: {str(e)}"

    def close(self):
        """Корректно закрывает браузер и освобождает ресурсы."""
        self.context.close()
        self.playwright.stop()


# Проверка работы движка при прямом запуске файла
if __name__ == "__main__":
    browser = BrowserEngine()
    print("Браузер запущен. Переходим на сайт...")
    print(browser.navigate_to_url("https://ya.ru"))
    time.sleep(3)
    browser.close()
    print("Браузер закрыт.")
