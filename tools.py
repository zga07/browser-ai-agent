import re
from typing import Any

from browser_engine import BrowserEngine
from dom_processor import DOMProcessor

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "navigate_to_url",
            "description": "Переходит по указанному веб-адресу (URL).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Полный адрес страницы, например 'https://www.wildberries.ru'."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_dom",
            "description": "Сканирует экран и возвращает список интерактивных элементов с их числовыми ID [0], [1], [2] (кнопки, ссылки, поля ввода, размеры). Вызывай перед каждым кликом или вводом!",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Необязательный поисковый фильтр (например 'поиск', 'размер', 'корзина'). Если пусто, возвращаются все элементы на экране."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Кликает по элементу по его числовому ID из списка query_dom, используя физические координаты.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "Числовой ID элемента из списка query_dom (например 0, 1, 5)."
                    },
                    "description": {
                        "type": "string",
                        "description": "Краткое описание действия для пользователя (например: 'выбор размера M', 'добавить в корзину')."
                    }
                },
                "required": ["index"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Вводит текст в поле ввода по его числовому ID из query_dom.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "Числовой ID поля ввода."
                    },
                    "text": {
                        "type": "string",
                        "description": "Текст для ввода."
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Нажать ли клавишу Enter после ввода текста (по умолчанию True)."
                    }
                },
                "required": ["index", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_page",
            "description": "Прокручивает страницу вниз или вверх для просмотра скрытых товаров, карточек или кнопок.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["down", "up"],
                        "description": "Направление прокрутки: 'down' (вниз) или 'up' (вверх)."
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Количество пикселей для прокрутки (по умолчанию 600)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Приостанавливает выполнение на 1-3 секунды для подгрузки динамического контента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "Количество секунд ожидания."
                    }
                },
                "required": ["seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Делает скриншот страницы. Вызывай перед завершением задачи.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Имя файла для сохранения, например 'order_screen.png'."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Завершает задачу и формирует итоговый отчет.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Подробный итог выполнения задачи."
                    }
                },
                "required": ["summary"]
            }
        }
    }
]


class ToolExecutor:
    def __init__(self, browser: BrowserEngine, dom_processor: DOMProcessor):
        self.browser = browser
        self.dom_processor = dom_processor
        # Ключевые корни потенциально опасных действий
        self.dangerous_keywords = [
            "оплат", "куп", "заказ", "удал", "спис", "очист",
            "pay", "buy", "order", "checkout", "delete", "clear", "remove"
        ]

    def _security_check(self, description: str) -> tuple[bool, str]:
        desc_lower = description.lower()
        if any(kw in desc_lower for kw in self.dangerous_keywords):
            print("\n⚠️  [SECURITY LAYER] Обнаружено чувствительное действие:")
            print(f"👉 Действие: {description}")
            choice = input("Подтвердить выполнение этого шага? (yes/no): ").strip().lower()
            if choice not in ["y", "yes", "да"]:
                return False, "Действие отменено пользователем в целях безопасности."
        return True, ""

    def _parse_index(self, args: dict[str, Any]) -> int:
        val = args.get("index")
        if val is None:
            val = args.get("selector") or args.get("id")
        if isinstance(val, int):
            return val
        match = re.search(r"\d+", str(val))
        return int(match.group(0)) if match else 0

    def execute(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "navigate_to_url":
                return self.browser.navigate_to_url(args["url"])

            elif name == "query_dom":
                query = args.get("query", "")
                text_summary, cache = self.dom_processor.query_dom(self.browser.page, query)
                self.browser.elements_cache = cache
                return text_summary

            elif name == "click_element":
                index = self._parse_index(args)
                desc = args.get("description", f"клик по элементу [{index}]")

                allowed, msg = self._security_check(desc)
                if not allowed:
                    return f"Action blocked: {msg}"

                return self.browser.click_element_by_id(index)

            elif name == "type_text":
                index = self._parse_index(args)
                text = args["text"]
                press_enter = args.get("press_enter", True)
                return self.browser.type_text_by_id(index, text, press_enter)

            elif name == "scroll_page":
                direction = args.get("direction", "down")
                amount = args.get("amount", 600)
                return self.browser.scroll_page(direction, amount)

            elif name == "wait":
                return self.browser.wait(args.get("seconds", 2))

            elif name == "take_screenshot":
                filename = args.get("filename", "screenshot.png")
                return self.browser.take_screenshot(filename)

            elif name == "finish_task":
                return f"Task completed: {args.get('summary', 'Готово.')}"

            else:
                return f"Unknown tool: {name}"

        except Exception as e:
            return f"Error executing tool {name}: {e!s}"
