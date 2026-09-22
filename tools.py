from typing import Dict, Any, Tuple
from browser_engine import BrowserEngine
from dom_processor import DOMProcessor

# 1. Описание инструментов (Tools Schema) для LLM
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
                        "description": "Полный адрес страницы, например 'https://lavka.yandex.ru' или 'https://hh.ru'."
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
            "description": "Запускает DOM Sub-agent для поиска элементов на текущей странице по естественному описанию. Возвращает подходящий CSS-селектор и описание найденного элемента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Что нужно найти на странице (например, 'поле поиска товаров', 'кнопка добавить в корзину', 'выбор адреса')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Кликает по элементу по указанному CSS-селектору.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS-селектор элемента, полученный от query_dom."
                    },
                    "description": {
                        "type": "string",
                        "description": "Краткое описание действия (например: 'клик по кнопке Оформить заказ', 'клик по товару')."
                    }
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Вводит текст в поле ввода по CSS-селектору.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS-селектор поля ввода."
                    },
                    "text": {
                        "type": "string",
                        "description": "Текст для ввода."
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Нужно ли нажать клавишу Enter после ввода текста (по умолчанию True)."
                    }
                },
                "required": ["selector", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Приостанавливает выполнение на указанное количество секунд для загрузки страницы или модального окна.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "Количество секунд ожидания (рекомендуется 2-3 секунды)."
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
            "description": "Делает скриншот текущего состояния страницы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Имя файла для сохранения, например 'screenshot.png'."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Задает уточняющий вопрос пользователю, если не хватает данных для продолжения (например: 'Какой адрес доставки выбрать?').",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Вопрос для пользователя."
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Завершает выполнение задачи и формирует финальный отчет для пользователя.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Итог выполнения задачи (что было найдено, добавлено в корзину, финальная сумма и статус)."
                    }
                },
                "required": ["summary"]
            }
        }
    }
]


# 2. Исполнитель инструментов и Security Layer
class ToolExecutor:
    def __init__(self, browser: BrowserEngine, dom_processor: DOMProcessor):
        self.browser = browser
        self.dom_processor = dom_processor

        # Ключевые слова потенциально деструктивных действий (Security Layer)
        self.dangerous_keywords = [
            "оплатить", "купить", "заказать", "удалить",
            "pay", "buy", "order", "checkout", "delete", "purchase"
        ]

    def _security_check(self, description: str, selector: str) -> Tuple[bool, str]:
        """
        Security Layer: проверяет, является ли действие деструктивным/финансовым,
        и запрашивает подтверждение у человека в консоли.
        """
        combined = f"{description} {selector}".lower()
        is_risky = any(kw in combined for kw in self.dangerous_keywords)

        if is_risky:
            print("\n⚠️  [SECURITY LAYER] Обнаружено чувствительное действие:")
            print(f"👉 Действие: {description or selector}")
            choice = input("Подтвердить выполнение этого шага? (yes/no): ").strip().lower()
            if choice not in ["y", "yes", "да"]:
                return False, "Действие отменено пользователем в целях безопасности."
        return True, ""

    def execute(self, name: str, args: Dict[str, Any]) -> str:
        """Маршрутизирует вызов инструмента в соответствующий метод."""
        try:
            if name == "navigate_to_url":
                return self.browser.navigate_to_url(args["url"])

            elif name == "query_dom":
                return self.dom_processor.query_dom(self.browser.page, args["query"])

            elif name == "click_element":
                desc = args.get("description", "")
                selector = args["selector"]

                # Проверка безопасности перед кликом
                allowed, msg = self._security_check(desc, selector)
                if not allowed:
                    return f"Action blocked: {msg}"

                return self.browser.click_element(selector)

            elif name == "type_text":
                selector = args["selector"]
                text = args["text"]
                res = self.browser.type_text(selector, text)
                if args.get("press_enter", True):
                    self.browser.page.keyboard.press("Enter")
                return res

            elif name == "wait":
                return self.browser.wait(args.get("seconds", 2))

            elif name == "take_screenshot":
                filename = args.get("filename", "screenshot.png")
                return self.browser.take_screenshot(filename)

            elif name == "ask_user":
                print(f"\n❓ [Агент спрашивает]: {args['question']}")
                answer = input("Твой ответ: ").strip()
                return f"User answered: {answer}"

            elif name == "finish_task":
                return f"Task completed: {args['summary']}"

            else:
                return f"Unknown tool: {name}"

        except Exception as e:
            return f"Error executing tool {name}: {str(e)}"
