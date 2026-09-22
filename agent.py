import json
import os
import time
from typing import Any, cast

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from rich.console import Console
from rich.panel import Panel

from tools import TOOLS_SCHEMA, ToolExecutor

load_dotenv()
console = Console()

SYSTEM_PROMPT = """
Ты — автономный веб-ассистент, управляющий браузером для решения задач пользователя.
Ты взаимодействуешь со страницами по числовым ID элементов [Set-of-Mark] и физическим координатам.

СТРАТЕГИЯ И ПРАВИЛА:
1. Исследование страницы:
   - Перед кликом или вводом текста ВСЕГДА вызывай `query_dom`, чтобы получить актуальный список элементов на экране с их числовыми ID [0], [1], [2]...
   - Для клика используй `click_element(index=ID, description="...")`.
   - Для ввода текста используй `type_text(index=ID, text="...")`.
2. Специфика интернет-магазинов (Wildberries, Ozon и др.):
   - При покупке одежды или обуви ВСЕГДА сначала выбери размер (кликни по элементу с размером: S, M, L, 48, 50 и т.д.), и только потом нажимай «Добавить в корзину» или «Купить сейчас».
   - Если нужный товар, размер или кнопка не видны на экране — используй `scroll_page(direction="down")`, а затем снова вызови `query_dom`.
3. Оптимизация скорости:
   - Не вызывай `wait`, если страница уже загружена.
   - Делай скриншот (`take_screenshot`) ТОЛЬКО перед вызовом `finish_task` или при критической ошибке.
4. Безопасность (Security Layer):
   - Всегда передавай понятное описание в поле `description` инструмента `click_element` (например: 'переход к оформлению заказа', 'удаление писем').
5. Верификация и завершение:
    - После клика по кнопкам действий (удалить, купить, очистить) ВСЕГДА вызывай `query_dom` С ПУСТЫМ ЗАПРОСОМ (`query=""`), чтобы увидеть всё всплывающее окно целиком.
    - Если открылось модальное окно с подтверждением — найди кнопку согласия («ОК», «Да», «Подтвердить», «Продолжить») и нажми её.
    - Вызывай `finish_task` только после того, как подтвердил действие в модальном окне и проверил, что список писем/товаров изменился.
"""


class BrowserAgent:
    def __init__(
        self,
        tool_executor: ToolExecutor,
        model: str | None = None,
        max_steps: int = 35
    ):
        self.executor = tool_executor
        self.model = model or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.max_steps = max_steps
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        self.messages: list[Any] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def run(self, user_goal: str):
        self.messages.append({"role": "user", "content": user_goal})
        console.print(Panel(f"[bold green]Новая задача:[/bold green] {user_goal}", title="Browser Agent"))

        step = 0
        while step < self.max_steps:
            step += 1
            time.sleep(1.0)

            response = None
            max_retries = 4
            backoff_delays = [5, 12, 20, 30]

            for attempt in range(max_retries):
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=cast(Any, self.messages),
                        tools=cast(Any, TOOLS_SCHEMA),
                        tool_choice="auto"
                    )
                    break
                except RateLimitError:
                    wait_sec = 20
                    console.print(f"[yellow]Лимит запросов (429). Ждём {wait_sec} сек... (попытка {attempt + 1}/{max_retries})[/yellow]")
                    time.sleep(wait_sec)
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_sec = backoff_delays[attempt]
                        console.print(f"[yellow]Сервер временно занят (503/сеть). Пауза {wait_sec} сек перед повтором... (попытка {attempt + 1}/{max_retries})[/yellow]")
                        time.sleep(wait_sec)
                    else:
                        console.print(f"[bold red]Не удалось связаться с LLM API после {max_retries} попыток:[/bold red] {e!s}")
                        return

            if not response:
                console.print("[bold red]Не удалось получить ответ от API.[/bold red]")
                break

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            self.messages.append(response_message.model_dump(exclude_none=True))

            if response_message.content:
                console.print(f"\n[bold blue]Assistant:[/bold blue] {response_message.content}")

            if not tool_calls:
                console.print("\n[yellow]Агент завершил рассуждения без вызова инструментов.[/yellow]")
                break

            for tool_call in tool_calls:
                func = getattr(tool_call, "function", None)
                if not func:
                    continue

                function_name = func.name
                try:
                    arguments = json.loads(func.arguments) if isinstance(func.arguments, str) else func.arguments
                except (json.JSONDecodeError, TypeError):
                    arguments = {}

                console.print(f"\n[cyan]🛠️  Using tool:[/cyan] [bold]{function_name}[/bold]")
                console.print(f"[dim]Input:[/dim] {json.dumps(arguments, ensure_ascii=False, indent=2)}")

                result = self.executor.execute(function_name, arguments)

                # Сокращаем вывод в консоль для длинных списков query_dom, чтобы не захламлять терминал
                log_result = result[:250] + " ... [список сокращен]" if len(str(result)) > 300 else result
                console.print(f"[green]Result:[/green] {log_result}")

                # Если это был срез DOM, сохраняем его в историю
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })

                # ОПТИМИЗАЦИЯ: заменяем старые простыни query_dom в истории на краткую заглушку
                # Оставляем полным только самый свежий ответ
                dom_count = 0
                for msg in reversed(self.messages):
                    if msg.get("role") == "tool" and "Интерактивные элементы" in str(msg.get("content", "")):
                        dom_count += 1
                        if dom_count > 1:
                            msg["content"] = "[Срез элементов страницы успешно обработан на предыдущем шаге]"

                if function_name == "finish_task":
                    summary = arguments.get("summary", "Задача успешно завершена.")
                    console.print(Panel(f"[bold green]Задача успешно выполнена![/bold green]\n\n{summary}", title="Отчёт агента"))
                    return

            if step >= self.max_steps:
                console.print(f"\n[bold yellow]Достигнут лимит шагов ({self.max_steps}).[/bold yellow]")
                choice = input("Добавить еще 15 шагов для продолжения выполнения? (y/n): ").strip().lower()
                if choice in ["y", "yes", "да"]:
                    self.max_steps += 15
                    continue
                else:
                    console.print("[bold red]Выполнение остановлено пользователем.[/bold red]")
                    break
