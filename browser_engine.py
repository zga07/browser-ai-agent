import os
import sys
import time
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright


class BrowserEngine:
    def __init__(self, user_data_dir: str = "./browser_profile"):
        self.user_data_dir = os.path.abspath(user_data_dir)
        self.playwright = sync_playwright().start()

        self.context: BrowserContext = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=False,
                    viewport={"width": 1280, "height": 800},
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized",
                        "--hide-crash-restore-bubble",
                        "--disable-session-crashed-bubble",
                        "--disable-infobars"
                    ]
                )

        self.page: Page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.elements_cache: dict[int, dict[str, Any]] = {}

    def navigate_to_url(self, url: str) -> str:
        """Переходит по указанному URL и сбрасывает кэш разметки."""
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        try:
            self.elements_cache.clear()
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return f"Successfully navigated to {url}"
        except Exception as e:
            return f"Error navigating to {url}: {e!s}"

    def click_element_by_id(self, index: int) -> str:
        """Выполняет клик по физическим экранным координатам элемента (Bounding Box)."""
        if index not in self.elements_cache:
            return f"Элемент [{index}] не найден в текущем срезе страницы. Сначала вызови query_dom."

        el_info = self.elements_cache[index]
        x, y = el_info["x"], el_info["y"]
        label = el_info.get("label", f"ID {index}")

        try:
            # 1. Физический клик мышью по вычисленным координатам центра элемента
            self.page.mouse.click(x, y)
            time.sleep(0.5)
            return f"Successfully clicked element [{index}] ('{label}') at ({x}, {y})"
        except Exception:
            # 2. Резервный клик через Playwright Locator по выставленному маркеру data-agent-id
            try:
                locator = self.page.locator(f'[data-agent-id="{index}"]')
                locator.click(timeout=2000, force=True)
                time.sleep(0.5)
                return f"Successfully force-clicked element [{index}] ('{label}')"
            except Exception as e2:
                return f"Failed to click element [{index}]: {e2!s}"

    def type_text_by_id(self, index: int, text: str, press_enter: bool = True) -> str:
        """Фокусирует поле ввода по координатам и вводит текст."""
        if index not in self.elements_cache:
            return f"Поле ввода [{index}] не найдено. Сначала вызови query_dom."

        el_info = self.elements_cache[index]
        x, y = el_info["x"], el_info["y"]
        label = el_info.get("label", f"ID {index}")

        try:
            # Кликаем по координатам, чтобы гарантированно дать фокус инпуту
            self.page.mouse.click(x, y)
            time.sleep(0.2)

            # Пробуем заполнить через Playwright locator, если элемент доступен
            locator = self.page.locator(f'[data-agent-id="{index}"]')
            if locator.count() > 0:
                locator.fill(text)
            else:
                # Очищаем поле комбинацией клавиш и печатаем текст
                select_all = "Meta+A" if sys.platform == "darwin" else "Control+A"
                self.page.keyboard.press(select_all)
                self.page.keyboard.press("Backspace")
                self.page.keyboard.type(text)

            if press_enter:
                self.page.keyboard.press("Enter")

            time.sleep(0.5)
            return f"Successfully typed '{text}' into element [{index}] ('{label}')"
        except Exception as e:
            return f"Failed to type into [{index}]: {e!s}"

    def scroll_page(self, direction: str = "down", amount: int = 600) -> str:
        """Прокручивает страницу вниз или вверх."""
        delta = amount if direction == "down" else -amount
        try:
            self.page.evaluate(f"window.scrollBy(0, {delta})")
            time.sleep(0.8)
            return f"Scrolled {direction} by {amount}px"
        except Exception as e:
            return f"Failed to scroll: {e!s}"

    def wait(self, seconds: int) -> str:
        time.sleep(seconds)
        return f"Waited for {seconds} seconds"

    def take_screenshot(self, filename: str = "screenshot.png") -> str:
        try:
            output_dir = "screenshots"
            os.makedirs(output_dir, exist_ok=True)
            clean_name = os.path.basename(filename)
            if not clean_name.endswith((".png", ".jpg", ".jpeg")):
                clean_name += ".png"
            filepath = os.path.join(output_dir, clean_name)
            self.page.screenshot(path=filepath, full_page=False)
            return f"Screenshot saved to {filepath}"
        except Exception as e:
            return f"Failed to take screenshot: {e!s}"

    def close(self):
        self.context.close()
        self.playwright.stop()
