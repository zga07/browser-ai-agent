import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import Page

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

    function cleanText(str) {
        return (str || '').trim().replace(/\\s+/g, ' ');
    }

    function getSelector(el) {
            // Безопасная запись ID в кавычках, чтобы двоеточия Gmail не ломали CSS-парсер
            if (el.id) return `[id="${el.id.replace(/"/g, '\\\\"')}"]`;

            const testId = el.getAttribute('data-testid');
            if (testId) return `[data-testid="${testId}"]`;

            const tooltip = el.getAttribute('data-tooltip');
            if (tooltip) return `[data-tooltip="${tooltip}"]`;

            const title = el.getAttribute('title');
            if (title) return `[title="${title}"]`;

            const ariaLabel = el.getAttribute('aria-label');
            const tag = el.tagName.toLowerCase();
            if (ariaLabel) return `${tag}[aria-label="${ariaLabel}"]`;

            // Специфика Gmail и SPA: ссылки с хэшем (#spam, #inbox, #trash)
            if (tag === 'a') {
                const href = el.getAttribute('href') || '';
                if (href.includes('#')) {
                    const hash = href.split('#')[1];
                    if (hash) return `a[href*="#${hash}"]`;
                }
            }

            const text = cleanText(el.innerText || el.textContent || el.value || '').slice(0, 35);

            // Проверяем интерактивного родителя
            const parentBtn = el.closest('button, a, [role="button"], [role="menuitem"]');
            if (parentBtn && parentBtn !== el) {
                if (parentBtn.id) return `[id="${parentBtn.id.replace(/"/g, '\\\\"')}"]`;
                const pTooltip = parentBtn.getAttribute('data-tooltip');
                if (pTooltip) return `[data-tooltip="${pTooltip}"]`;
                const pAria = parentBtn.getAttribute('aria-label');
                if (pAria) return `[aria-label="${pAria}"]`;
                const pTitle = parentBtn.getAttribute('title');
                if (pTitle) return `[title="${pTitle}"]`;
                const parentText = cleanText(parentBtn.innerText || parentBtn.textContent || '').slice(0, 35);
                if (parentText) {
                    return `text="${parentText.replace(/"/g, '\\\\"')}"`;
                }
            }

            if (text) {
                if (tag === 'button') return `button:has-text("${text.replace(/"/g, '\\\\"')}")`;
                if (tag === 'a') return `a:has-text("${text.replace(/"/g, '\\\\"')}")`;
                return `text="${text.replace(/"/g, '\\\\"')}"`;
            }

            const placeholder = el.getAttribute('placeholder');
            if (placeholder) return `[placeholder="${placeholder}"]`;

            return '';
        }

    const interactiveSelectors = [
        'button', 'a[href]', 'input', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="menuitem"]', '[role="tab"]',
        '[data-tooltip]', '[tabindex]:not([tabindex="-1"])'
    ];

    const rawElements = Array.from(document.querySelectorAll(interactiveSelectors.join(', ')));
    const result = [];
    let counter = 0;

    for (const el of rawElements) {
        if (!isVisible(el)) continue;

        const text = cleanText(el.innerText || el.textContent || el.value || '').slice(0, 80);
        const ariaLabel = el.getAttribute('aria-label') || '';
        const title = el.getAttribute('title') || '';
        const tooltip = el.getAttribute('data-tooltip') || '';
        const placeholder = el.getAttribute('placeholder') || '';
        const selector = getSelector(el);

        // Отбрасываем элементы, для которых не удалось построить надежный селектор
        if (!selector || (!text && !placeholder && !ariaLabel && !title && !tooltip && !el.id)) {
            continue;
        }

        const label = text || ariaLabel || title || tooltip || placeholder;

        result.push({
            id: counter++,
            selector: selector,
            label: label
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

    def extract_elements(self, page: Page) -> list[dict[str, Any]]:
        try:
            return page.evaluate(EXTRACT_INTERACTIVE_ELEMENTS_JS)
        except Exception as e:
            return [{"error": f"Failed to extract elements: {e!s}"}]

    def query_dom(self, page: Page, query: str) -> str:
        elements = self.extract_elements(page)

        if not elements or ("error" in elements[0] and len(elements) == 1):
            return "Не удалось извлечь элементы со страницы."

        # Отправляем модели только ID и текстовое описание (без селекторов!)
        simplified_elements = [
            {"id": el["id"], "text": el["label"]}
            for el in elements
            if "id" in el and "label" in el
        ]

        system_prompt = (
            "Ты — вспомогательный DOM Sub-agent. Твоя задача — сопоставить поисковый запрос "
            "пользователя с элементом на веб-странице.\n"
            "Инструкция:\n"
            "1. Найди в переданном списке элемент, максимально подходящий по смыслу.\n"
            "2. Верни СТРОГО одну строку в формате:\n"
            "ID: <номер_элемента>\n"
            "Например: ID: 5\n"
            "3. Если ни один элемент не подходит, ответь: ID: none"
        )

        user_content = (
            f"Запрос агента: {query}\n\n"
            f"Список элементов на странице:\n"
            f"{json.dumps(simplified_elements, ensure_ascii=False, indent=1)}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            )
            reply = response.choices[0].message.content or ""

            # Ищем ID в ответе модели
            match = re.search(r"ID:\s*(\d+)", reply, re.IGNORECASE)
            if not match:
                return "Подходящий элемент не найден на странице."

            target_id = int(match.group(1))
            matched_el = next((el for el in elements if el.get("id") == target_id), None)

            if not matched_el:
                return "Элемент с указанным ID не найден."

            return f"Селектор: {matched_el['selector']} | Описание: {matched_el['label']}"

        except Exception as e:
            return f"Ошибка при работе DOM Sub-agent: {e!s}"
