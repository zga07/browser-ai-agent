import re
from typing import Any

from playwright.sync_api import Page

EXTRACT_SET_OF_MARK_JS = """
() => {
    // 1. Очищаем старые маркеры
    document.querySelectorAll('[data-agent-id]').forEach(el => el.removeAttribute('data-agent-id'));

    function isVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 3 && rect.height > 3 &&
               rect.bottom >= 0 && rect.top <= window.innerHeight &&
               rect.right >= 0 && rect.left <= window.innerWidth;
    }

    function cleanText(str) {
        return (str || '').trim().replace(/\\s+/g, ' ');
    }

    const interactiveSelectors = [
        'button', 'a[href]', 'input', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="menuitem"]', '[role="tab"]',
        '[role="checkbox"]', '[role="radio"]', '[role="option"]',
        '[data-testid]', '[data-tooltip]', '[onclick]', '[tabindex]:not([tabindex="-1"])'
    ];

    // 1. Проверяем наличие активных модальных окон
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"], dialog, [aria-modal="true"]'))
        .filter(isVisible);

    let rawElements = [];

    // Приоритет №1: интерактивные элементы внутри модального окна ставим в НАЧАЛО
    if (dialogs.length > 0) {
        for (const d of dialogs) {
            const modalBtns = Array.from(d.querySelectorAll(interactiveSelectors.join(', ')));
            rawElements.push(...modalBtns);
        }
    }

    // Приоритет №2: остальные интерактивные элементы страницы
    rawElements.push(...Array.from(document.querySelectorAll(interactiveSelectors.join(', '))));

    // Дополнительно ищем кликабельные элементы с pointer
    const allDivsAndSpans = Array.from(document.querySelectorAll('div, span, li, label'));
    for (const el of allDivsAndSpans) {
        if (rawElements.length >= 150) break;
        if (window.getComputedStyle(el).cursor === 'pointer' && !rawElements.includes(el)) {
            rawElements.push(el);
        }
    }

    // Убираем дубликаты с сохранением приоритета модалок
    rawElements = Array.from(new Set(rawElements));

    const result = [];
    let counter = 0;

    for (const el of rawElements) {
        if (!isVisible(el)) continue;

        // Исключаем дочерние элементы уже учтенных кнопок/ссылок
        const parentInteractive = el.parentElement ? el.parentElement.closest('button, a[href], [role="button"]') : null;
        if (parentInteractive && parentInteractive !== el && isVisible(parentInteractive)) {
            continue;
        }

        const rect = el.getBoundingClientRect();
        const centerX = Math.round(rect.left + rect.width / 2);
        const centerY = Math.round(rect.top + rect.height / 2);

        // Назначаем атрибут в DOM для резервного клика
        el.setAttribute('data-agent-id', String(counter));

        const tag = el.tagName.toLowerCase();
        let text = cleanText(el.innerText || el.textContent || el.value || '');
        const placeholder = el.getAttribute('placeholder') || '';
        const ariaLabel = el.getAttribute('aria-label') || '';
        const title = el.getAttribute('title') || '';
        const role = el.getAttribute('role') || '';

        let label = text;
        if (!label) label = ariaLabel || title || placeholder;
        if (label.length > 70) label = label.slice(0, 70) + '...';

        if (!label && !placeholder && tag !== 'input') continue;

        result.push({
            id: counter,
            tag: tag,
            role: role,
            label: label,
            placeholder: placeholder,
            x: centerX,
            y: centerY,
            width: Math.round(rect.width),
            height: Math.round(rect.height)
        });

        counter++;
        if (result.length >= 100) break;
    }

    return result;
}
"""


class DOMProcessor:
    def extract_elements(self, page: Page) -> list[dict[str, Any]]:
        """Сканирует страницу через JS и размечает интерактивные элементы индексами."""
        try:
            return page.evaluate(EXTRACT_SET_OF_MARK_JS)
        except Exception as e:
            return [{"error": f"Failed to extract elements: {e!s}"}]

    def query_dom(self, page: Page, query: str = "") -> tuple[str, dict[int, dict[str, Any]]]:
        """
        Формирует текстовый список элементов вида [ID] tag: 'text'
        и кэш элементов для прямого физического клика по координатам.
        """
        elements = self.extract_elements(page)

        if not elements or ("error" in elements[0] and len(elements) == 1):
            return "Не удалось извлечь элементы со страницы. Попробуй проскроллить или подождать.", {}

        elements_cache: dict[int, dict[str, Any]] = {
            el["id"]: el for el in elements if "id" in el
        }

        # Фильтрация по ключевому слову
        filtered = elements
        if query and query.strip():
            words = [w.lower() for w in re.split(r"\s+", query.strip()) if len(w) > 1]
            matched = [
                el for el in elements
                if any(w in el.get("label", "").lower() or w in el.get("placeholder", "").lower() for w in words)
            ]
            # Если по запросу ничего не нашлось — возвращаем первые 35 элементов, чтобы агент не получал пустоту
            filtered = matched if matched else elements[:35]

        lines = []
        for el in filtered:
            tag_name = el.get("role") or el.get("tag", "element")
            label = el.get("label", "").strip()
            placeholder = el.get("placeholder", "").strip()

            desc = label
            if placeholder and placeholder not in desc:
                desc += f" (placeholder: {placeholder})"

            lines.append(f"[{el['id']}] {tag_name}: \"{desc}\"")

        output_text = "Интерактивные элементы на экране (используй [ID] для клика/ввода):\n" + "\n".join(lines)
        return output_text, elements_cache
