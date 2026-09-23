import os
import sys
import time
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright


class BrowserEngine:
    def __init__(self, user_data_dir: str = "./browser_profile"):
        """Инициализирует Chromium с сохранением сессии и принудительным однооконным режимом."""
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
                "--disable-infobars",
            ],
        )

        # Принудительно нейтрализуем открытие новых вкладок
        self.context.add_init_script("""
            window.open = (url) => {
                if (url) window.location.href = url;
                return window;
            };

            const neutralizeBlank = () => {
                document.querySelectorAll('a[target="_blank"]').forEach(a => {
                    a.removeAttribute('target');
                });
            };

            document.addEventListener('DOMContentLoaded', neutralizeBlank);
            const observer = new MutationObserver(neutralizeBlank);
            observer.observe(document.documentElement, { childList: true, subtree: true });
        """)

        # Автоматический перехват активной страницы, если сайт всё же создал новую
        def _on_new_page(new_p: Page):
            self._page = new_p
            self.elements_cache.clear()

        self.context.on("page", _on_new_page)

        self._page: Page | None = (
            self.context.pages[0] if self.context.pages else self.context.new_page()
        )
        self.elements_cache: dict[int, dict[str, Any]] = {}

    @property
    def page(self) -> Page:
        """Гарантирует возврат открытой и активной вкладки."""
        if self._page is None or self._page.is_closed():
            open_pages = [p for p in self.context.pages if not p.is_closed()]
            if open_pages:
                self._page = open_pages[-1]
            else:
                self._page = self.context.new_page()
            self.elements_cache.clear()
        return self._page

    def navigate_to_url(self, url: str) -> str:
        """Переходит по URL и сбрасывает кэш разметки."""
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        try:
            self.elements_cache.clear()
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return f"Successfully navigated to {url}"
        except Exception as e:
            return f"Error navigating to {url}: {e!s}"

    def click_element_by_id(self, index: int) -> str:
        """Скроллит к элементу и совершает физический клик по координатам."""
        if index not in self.elements_cache:
            return f"Ошибка: Элемент [{index}] не найден или устарел. ОБЯЗАТЕЛЬНО вызови query_dom, чтобы обновить разметку экрана."

        el_info = self.elements_cache[index]
        label = el_info.get("label", f"ID {index}")

        try:
            locator = self.page.locator(f'[data-agent-id="{index}"]').first
            if locator.count() > 0:
                locator.scroll_into_view_if_needed(timeout=2000)
                time.sleep(0.3)

                box = locator.bounding_box()
                if box:
                    click_x = box["x"] + box["width"] / 2
                    click_y = box["y"] + box["height"] / 2
                    self.page.mouse.click(click_x, click_y)
                else:
                    locator.click(force=True, timeout=2000)
            else:
                self.page.mouse.click(el_info["x"], el_info["y"])

            # Даем интерфейсу время на отрисовку модалки или счетчика
            time.sleep(0.8)
            self.elements_cache.clear()
            return f"Успешный клик по [{index}] ('{label}'). Страница обновилась! Вызови query_dom для следующего действия."

        except Exception as e:
            self.elements_cache.clear()
            return f"Failed to click element [{index}]: {e!s}"

    def type_text_by_id(self, index: int, text: str, press_enter: bool = True) -> str:
        """Вводит текст в поле с валидацией типа и резервным вводом через клавиатуру."""
        if index not in self.elements_cache:
            return f"Поле ввода [{index}] устарело. Сначала вызови query_dom."

        el_info = self.elements_cache[index]
        label = el_info.get("label", f"ID {index}")
        role = el_info.get("role", "")

        if role in ["radio", "checkbox"]:
            return f"ОШИБКА: Элемент [{index}] — это переключатель ({role}), в него нельзя вводить текст! Используй click_element."

        try:
            locator = self.page.locator(f'[data-agent-id="{index}"]').first
            if locator.count() > 0:
                locator.scroll_into_view_if_needed(timeout=2000)
                try:
                    locator.fill(text)
                except Exception:
                    locator.click(force=True)
                    select_all = "Meta+A" if sys.platform == "darwin" else "Control+A"
                    self.page.keyboard.press(select_all)
                    self.page.keyboard.press("Backspace")
                    self.page.keyboard.type(text)
            else:
                self.page.mouse.click(el_info["x"], el_info["y"])
                select_all = "Meta+A" if sys.platform == "darwin" else "Control+A"
                self.page.keyboard.press(select_all)
                self.page.keyboard.press("Backspace")
                self.page.keyboard.type(text)

            if press_enter:
                self.page.keyboard.press("Enter")

            time.sleep(0.6)
            self.elements_cache.clear()
            return f"Successfully typed '{text}' into [{index}] ('{label}'). Вызови query_dom для следующего шага."
        except Exception as e:
            self.elements_cache.clear()
            return f"Failed to type into [{index}]: {e!s}"

    def scroll_page(self, direction: str = "down", amount: int = 600) -> str:
        """Прокручивает страницу или контейнер списка с помощью эмуляции колеса мыши."""
        delta = amount if direction == "down" else -amount
        try:
            self.page.mouse.move(640, 400)
            self.page.mouse.wheel(0, delta)
            self.page.evaluate(f"window.scrollBy(0, {delta})")
            time.sleep(0.8)
            self.elements_cache.clear()
            return f"Scrolled {direction} by {amount}px"
        except Exception as e:
            return f"Failed to scroll: {e!s}"

    def press_key(self, key: str = "Escape") -> str:
        """Нажимает служебную клавишу (Escape для закрытия окон, Enter для подтверждения)."""
        try:
            self.page.keyboard.press(key)
            time.sleep(0.5)
            self.elements_cache.clear()
            return f"Нажата клавиша '{key}'. Вызови query_dom для проверки."
        except Exception as e:
            return f"Не удалось нажать клавишу '{key}': {e!s}"

    def go_back(self) -> str:
        """Возвращается на предыдущую страницу в истории браузера."""
        try:
            self.elements_cache.clear()
            self.page.go_back(wait_until="domcontentloaded", timeout=15000)
            time.sleep(0.5)
            return "Успешно вернулись назад. Вызови query_dom."
        except Exception as e:
            return f"Не удалось вернуться назад: {e!s}"

    def wait(self, seconds: int) -> str:
        """Приостанавливает выполнение на указанное количество секунд."""
        time.sleep(seconds)
        return f"Waited for {seconds} seconds"

    def take_screenshot(self, filename: str = "screenshot.png") -> str:
        """Делает снимок текущего экрана и сохраняет в папку screenshots/."""
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
        """Корректно закрывает контекст браузера и процесс Playwright."""
        try:
            if hasattr(self, "context") and self.context:
                self.context.close()
        except Exception:  # noqa: S110
            pass

        try:
            if hasattr(self, "playwright") and self.playwright:
                self.playwright.stop()
        except Exception:  # noqa: S110
            pass
