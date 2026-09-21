import os
import json
from typing import Dict, Any, List
from playwright.sync_api import Page
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# JS-скрипт собирает только интерактивные элементы со страницы
EXTRACT_INTERACTIVE_ELEMENTS_JS = """
() => {
    function isVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function getSelector(el) {
        if (el.id) return `#${el.id}`;

        let path = el.tagName.toLowerCase();
        if (el.name) return `${path}[name="${el.name}"]`;
        if (el.getAttribute('type')) return `${path}[type="${el.getAttribute('type')}"]`;
        if (el.getAttribute('role')) return `${path}[role="${el.getAttribute('role')}"]`;

        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\\s+/).filter(c => c && !c.includes(':'));
            if (classes.length > 0) {
                return `${path}.${classes.slice(0, 2).join('.')}`;
            }
        }
        return path;
    }

    const interactiveSelectors = [
        'button', 'a[href]', 'input', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="searchbox"]',
        '[tabindex]:not([tabindex="-1"])'
    ];

    const elements = document.querySelectorAll(interactiveSelectors.join(', '));
    const result = [];
    let counter = 0;

    for (const el of elements) {
        if (!isVisible(el)) continue;

        const text = (el.innerText || el.textContent || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 100);
        const placeholder = el.getAttribute('placeholder') || '';
        const ariaLabel = el.getAttribute('aria-label') || '';
        const selector = getSelector(el);

        if (!text && !placeholder && !ariaLabel && !el.id) continue;

        result.push({
            id: counter++,
            tag: el.tagName.toLowerCase(),
            selector: selector,
            text: text,
            placeholder: placeholder,
            aria_label: ariaLabel,
            type: el.getAttribute('type') || ''
        });

        if (result.length >= 60) break;
    }

    return result;
}
"""


class DOMProcessor:
    def __init__(self, model: str = None):
        """
        DOM Sub-agent анализирует выжимку интерактивных элементов
        и возвращает точные селекторы для главного агента.
        """
        self.model = model or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )

    def extract_elements(self, page: Page) -> List[Dict[str, Any]]:
        """Извлекает интерактивные элементы страницы без переполнения контекста токенами."""
        try:
            return page.evaluate(EXTRACT_INTERACTIVE_ELEMENTS_JS)
        except Exception as e:
            return [{"error": f"Failed to extract elements: {str(e)}"}]

    def query_dom(self, page: Page, query: str) -> str:
        """
        Sub-agent обрабатывает естественный запрос главного агента
        и возвращает найденный селектор и описание.
        """
        elements = self.extract_elements(page)

        if not elements or "error" in elements[0]:
            return "Не удалось извлечь элементы со страницы."

        elements_summary = json.dumps(elements, ensure_ascii=False, indent=1)

        system_prompt = (
            "Ты — вспомогательный DOM Sub-agent. Твоя задача — анализировать срез "
            "интерактивных элементов веб-страницы и находить элемент, соответствующий запросу агента.\n"
            "Правила:\n"
            "1. Найди наиболее подходящий элемент по тексту, placeholder или селектору.\n"
            "2. Укажи точный CSS-селектор для клика или ввода текста.\n"
            "3. Отвечай кратко и конкретно: есть ли элемент, какой селектор и что на нем написано."
        )

        user_content = (
            f"Запрос агента: {query}\n\n"
            f"Список интерактивных элементов на текущей странице:\n"
            f"{elements_summary}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Ошибка при работе DOM Sub-agent: {str(e)}"


# Проверка работы
if __name__ == "__main__":
    from browser_engine import BrowserEngine

    engine = BrowserEngine()
    engine.navigate_to_url("https://ya.ru")

    dom_sub_agent = DOMProcessor()
    print("Ищем поисковую строку через Sub-agent...")
    answer = dom_sub_agent.query_dom(engine.page, "Есть ли поле для ввода поискового запроса? Какой у него селектор?")
    print("\nОтвет DOM Sub-agent:\n", answer)

    engine.close()
