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
                        "description": "Полный адрес страницы, например 'https://lavka.yandex.ru'."
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
            "description": "Сканирует экран и возвращает актуальный список всех видимых интерактивных элементов с их ID [0], [1], [2]. Обязательно вызывай перед КАЖДЫМ действием (клик, ввод) и сразу после wait.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Кликает по элементу по его числовому ID из последнего вызова query_dom.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "Числовой ID элемента из списка query_dom."
                    },
                    "description": {
                        "type": "string",
                        "description": "Краткое описание действия (например: 'добавить воду в корзину', 'открыть поиск')."
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
            "description": "Вводит текст в поле ввода (input-text или textarea) по его числовому ID из query_dom.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "Числовой ID текстового поля."
                    },
                    "text": {
                        "type": "string",
                        "description": "Текст для ввода."
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Нажать ли Enter после ввода текста (по умолчанию True)."
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
            "description": "Прокручивает страницу или активный контейнер вниз или вверх.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["down", "up"],
                        "description": "Направление прокрутки: 'down' или 'up'."
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
            "name": "press_key",
            "description": "Нажимает служебную клавишу клавиатуры ('Escape' для закрытия попапов, 'Enter' для подтверждения).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "enum": ["Escape", "Enter", "Tab", "Backspace"],
                        "description": "Клавиша для нажатия."
                    }
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "go_back",
            "description": "Возвращается на предыдущую страницу в истории браузера (кнопка 'Назад').",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Приостанавливает выполнение на 1-2 секунды. ВНИМАНИЕ: Сразу после wait ты ОБЯЗАН вызвать query_dom перед следующим кликом или вводом!",
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
            "description": "Делает снимок текущего экрана и сохраняет в screenshots/.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Имя файла скриншота, например 'cart_state.png'."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Завершает задачу и формирует структурированный отчет. Вызывай ТОЛЬКО после проверки финального состояния на экране.",
            "parameters": {
                "type": "object",
                "properties": {
                    "completed_items": {
                        "type": "array",
                        "description": "Список конкретных объектов, с которыми действие РЕАЛЬНО завершено (добавлены в корзину, отправлены отклики, перемещены письма).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "Точное наименование товара, вакансии или тема письма."
                                },
                                "details": {
                                    "type": "string",
                                    "description": "Фактическая цена/зарплата, объем, компания с экрана."
                                },
                                "result_status": {
                                    "type": "string",
                                    "description": "Статус (например: 'Добавлено в корзину (1 шт)', 'Отклик успешно отправлен')."
                                }
                            },
                            "required": ["title", "details", "result_status"]
                        }
                    },
                    "final_comment": {
                        "type": "string",
                        "description": "Общий честный итог выполнения и возникшие сложности (если были)."
                    }
                },
                "required": ["completed_items", "final_comment"]
            }
        }
    }
]


class ToolExecutor:
    def __init__(self, browser: BrowserEngine, dom_processor: DOMProcessor):
        self.browser = browser
        self.dom_processor = dom_processor

    def _security_check(self, description: str) -> tuple[bool, str]:
        desc_lower = description.lower()

        # Белый список: безопасные действия в корзине, поиске, формах
        safe_exceptions = [
            "фильтр", "filter", "поиск", "запрос",
            "текст", "символ", "ввод", "тег",
            "в корзину", "добавить", "спам", "пометить", "чекбокс",
            "отклик", "откликнуться", "резюме", "сопроводительное", "выбор"
        ]
        if any(safe in desc_lower for safe in safe_exceptions):
            return True, ""

        # Реально необратимые финансовые и критические операции
        critical_keywords = [
            "оплатить", "купить заказ", "списать деньги", "перевести",
            "подтвердить оплату", "удалить навсегда", "очистить корзину", "удалить все"
        ]

        if any(kw in desc_lower for kw in critical_keywords):
            print("\n⚠️  [SECURITY LAYER] Обнаружено критическое действие:")
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
                text_summary, cache = self.dom_processor.query_dom(self.browser.page)
                self.browser.elements_cache = cache
                return text_summary

            elif name == "go_back":
                return self.browser.go_back()

            elif name == "press_key":
                return self.browser.press_key(args.get("key", "Escape"))

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
                res = self.browser.wait(args.get("seconds", 2))
                return f"{res}. ОБЯЗАТЕЛЬНО вызови query_dom следующим шагом перед любым действием!"

            elif name == "take_screenshot":
                filename = args.get("filename", "screenshot.png")
                return self.browser.take_screenshot(filename)

            elif name == "finish_task":
                return "TASK_FINISHED"

            else:
                return f"Unknown tool: {name}"

        except Exception as e:
            return f"Error executing tool {name}: {e!s}"
