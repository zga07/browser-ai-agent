import os
import json
from typing import Dict, Any, List
from playwright.sync_api import Page
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

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

        const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 30);
        const tag = el.tagName.toLowerCase();

        if (el.getAttribute('data-testid')) {
            return `[data-testid="${el.getAttribute('data-testid')}"]`;
        }
        if (el.getAttribute('aria-label')) {
            return `${tag}[aria-label="${el.getAttribute('aria-label')}"]`;
        }
        if (text && (tag === 'button' || tag === 'a' || tag === 'span' || tag === 'div')) {
            return `text="${text.replace(/"/g, '\\"')}"`;
        }

        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\\s+/).filter(c => c && !c.includes(':') && !c.includes('/'));
            if (classes.length > 0) {
                return `${tag}.${classes.slice(0, 2).join('.')}`;
            }
        }
        return tag;
    }

    const interactiveSelectors = [
        'button', 'a[href]', 'input', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="dialog"] button',
        '[tabindex]:not([tabindex="-1"])'
    ];

    const elements = Array.from(document.querySelectorAll(interactiveSelectors.join(', ')));
    const result = [];
    let counter = 0;

    for (const el of elements) {
        if (!isVisible(el)) continue;

        const text = (el.innerText || el.textContent || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
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
            aria_label: ariaLabel
        });

        if (result.length >= 120) break;
    }

    return result;
}
"""


class DOMProcessor:
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )

    def extract_elements(self, page: Page) -> List[Dict[str, Any]]:
        try:
            return page.evaluate(EXTRACT_INTERACTIVE_ELEMENTS_JS)
        except Exception as e:
            return [{"error": f"Failed to extract elements: {str(e)}"}]

    def query_dom(self, page: Page, query: str) -> str:
        elements = self.extract_elements(page)

        if not elements or ("error" in elements[0] and len(elements) == 1):
            return "Не удалось извлечь элементы со страницы."

        elements_summary = json.dumps(elements, ensure_ascii=False, indent=1)

        system_prompt = (
            "Ты — вспомогательный DOM Sub-agent. Твоя задача — анализировать срез "
            "интерактивных элементов веб-страницы и возвращать наиболее подходящий элемент для клика/ввода.\n"
            "Правила:\n"
            "1. Найди элемент, соответствующий запросу агента.\n"
            "2. ОБЯЗАТЕЛЬНО укажи поле `selector` и точный текст `text` элемента.\n"
            "3. Формат ответа строго: Селектор: <selector> | Описание: <text>"
        )

        user_content = (
            f"Запрос агента: {query}\n\n"
            f"Список интерактивных элементов на странице:\n"
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
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"Ошибка при работе DOM Sub-agent: {str(e)}"
