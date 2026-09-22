import os
import time

from playwright.sync_api import BrowserContext, Page, sync_playwright


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
            return f"Error navigating to {url}: {e!s}"

    def click_element(self, selector: str) -> str:
            """Кликает по элементу с защитой от пустых селекторов и зависаний."""
            # Блокируем голые неспецифичные теги
            if selector.strip() in {"a", "span", "div", "button", "p", "input"}:
                return f"Failed to click '{selector}'. Reason: Селектор слишком общий. Нужен уточняющий атрибут или текст."

            try:
                self.page.click(selector, timeout=5000)
                return f"Successfully clicked: {selector}"
            except Exception as e:
                try:
                    self.page.click(selector, force=True, timeout=3000)
                    return f"Successfully force-clicked: {selector}"
                except Exception:
                    return f"Failed to click '{selector}'. Reason: {e!s}"

    def type_text(self, selector: str, text: str) -> str:
        """Вводит текст в поле."""
        try:
            self.page.wait_for_selector(selector, state="visible", timeout=7000)
            self.page.fill(selector, text)
            return f"Successfully typed '{text}' into {selector}"
        except Exception as e:
            return f"Failed to type into '{selector}'. Reason: {e!s}"

    def wait(self, seconds: int) -> str:
        """Делает паузу (нужна для ожидания динамического контента)."""
        time.sleep(seconds)
        return f"Waited for {seconds} seconds"

    def take_screenshot(self, filename: str = "screenshot.png") -> str:
            """Делает скриншот и сохраняет его в отдельную папку screenshots/."""
            try:
                output_dir = "screenshots"
                os.makedirs(output_dir, exist_ok=True)

                # Берем только имя файла, исключая случайные пути
                clean_name = os.path.basename(filename)
                if not clean_name.endswith((".png", ".jpg", ".jpeg")):
                    clean_name += ".png"

                filepath = os.path.join(output_dir, clean_name)
                self.page.screenshot(path=filepath, full_page=False)
                return f"Screenshot saved to {filepath}"
            except Exception as e:
                return f"Failed to take screenshot: {e!s}"

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
