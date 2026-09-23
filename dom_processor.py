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
        return rect.width > 5 && rect.height > 5 &&
               rect.bottom >= 0 && rect.top <= window.innerHeight &&
               rect.right >= 0 && rect.left <= window.innerWidth;
    }

    function cleanText(str) {
        return (str || '').trim().replace(/\\s+/g, ' ');
    }

    // Интерактивные селекторы без шумного [data-testid]
    const interactiveSelectors = [
        'button', 'a[href]', 'input', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="menuitem"]', '[role="tab"]',
        '[role="checkbox"]', '[role="radio"]', '[role="option"]',
        '[data-tooltip]', '[onclick]', '[tabindex]:not([tabindex="-1"])'
    ];

    // Проверяем наличие активных диалоговых/модальных окон
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"], dialog, [aria-modal="true"]'))
        .filter(isVisible);

    let rawElements = [];
    if (dialogs.length > 0) {
        for (const d of dialogs) {
            rawElements.push(...Array.from(d.querySelectorAll(interactiveSelectors.join(', '))));
        }
    }
    rawElements.push(...Array.from(document.querySelectorAll(interactiveSelectors.join(', '))));

    const allClickables = Array.from(document.querySelectorAll('div, span, li, label'));
    for (const el of allClickables) {
        if (rawElements.length >= 150) break;
        if (window.getComputedStyle(el).cursor === 'pointer' && !rawElements.includes(el)) {
            rawElements.push(el);
        }
    }

    rawElements = Array.from(new Set(rawElements));

    const result = [];
    let counter = 0;

    for (const el of rawElements) {
        if (!isVisible(el)) continue;

        const tag = el.tagName.toLowerCase();
        // Исключаем чисто графические и декоративные теги
        if (tag === 'img' || tag === 'svg' || el.getAttribute('role') === 'presentation') {
            continue;
        }

        // Исключаем дочерние элементы кнопок
        const parentBtn = el.parentElement ? el.parentElement.closest('button, [role="button"]') : null;
        if (parentBtn && parentBtn !== el && isVisible(parentBtn)) {
            continue;
        }

        let role = el.getAttribute('role') || '';
        const inputType = (el.getAttribute('type') || 'text').toLowerCase();

        if (tag === 'input') {
            if (inputType === 'radio') role = 'radio';
            else if (inputType === 'checkbox') role = 'checkbox';
            else if (['submit', 'button'].includes(inputType)) role = 'button';
            else role = 'input-text';
        } else if (tag === 'textarea') {
            role = 'textarea';
        }

        let text = cleanText(el.innerText || el.textContent || el.value || '');
        const placeholder = el.getAttribute('placeholder') || '';
        const ariaLabel = el.getAttribute('aria-label') || '';
        const title = el.getAttribute('title') || '';

        // Распознавание кнопок с иконками без текста
        if (!text && (tag === 'button' || role === 'button')) {
            if (ariaLabel) text = ariaLabel;
            else if (el.querySelector('svg')) text = '+ (Добавить)';
        }

        // Обогащение текста кнопок контекстом родительской карточки
        const cardParent = el.closest('article, [class*="product"], [class*="card"], [class*="item"], [data-qa*="vacancy"]');
        if (cardParent && (tag === 'button' || role === 'button')) {
            const cardText = cleanText(cardParent.innerText || '');
            const action = text || 'В корзину';
            if (cardText && !action.includes(cardText.slice(0, 15))) {
                text = action + ' [Товар: ' + cardText.slice(0, 45) + ']';
            }
        }

        let label = text || ariaLabel || title || placeholder;
        if (label.length > 90) label = label.slice(0, 90) + '...';

        if (!label && !placeholder && !['input-text', 'textarea'].includes(role)) {
            continue;
        }

        const rect = el.getBoundingClientRect();
        const centerX = Math.round(rect.left + rect.width / 2);
        const centerY = Math.round(rect.top + rect.height / 2);

        // Присваиваем ID строго после всех валидаций
        el.setAttribute('data-agent-id', String(counter));

        result.push({
            id: counter,
            tag: tag,
            role: role || tag,
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

    def query_dom(self, page: Page) -> tuple[str, dict[int, dict[str, Any]]]:
        """Формирует список интерактивных элементов и кэш для координатных кликов."""
        elements = self.extract_elements(page)

        if not elements or ("error" in elements[0] and len(elements) == 1):
            return "Не удалось извлечь элементы со страницы. Попробуй проскроллить или подождать.", {}

        elements_cache: dict[int, dict[str, Any]] = {
            el["id"]: el for el in elements if "id" in el
        }

        lines = []
        for el in elements:
            role_or_tag = el.get("role") or el.get("tag", "element")
            label = el.get("label", "").strip()
            placeholder = el.get("placeholder", "").strip()

            desc = label
            if placeholder and placeholder not in desc:
                desc += f" (placeholder: {placeholder})"

            lines.append(f"[{el['id']}] {role_or_tag}: \"{desc}\"")

        output_text = "Интерактивные элементы на экране (используй [ID] для клика/ввода):\n" + "\n".join(lines)
        return output_text, elements_cache
