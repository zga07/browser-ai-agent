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
Ты — автономный веб-ассистент, который управляет браузером для выполнения задач пользователя.
Твоя цель — решить поставленную задачу от начала до конца, исследуя веб-страницы в реальном времени.

ПРАВИЛА И СТРАТЕГИЯ:
1. Исследование страниц:
   - Никогда не угадывай селекторы наугад.
   - Перед кликом или вводом текста ВСЕГДА используй инструмент `query_dom`, чтобы DOM Sub-agent нашел актуальный CSS-селектор элемента.
2. Автономность и обработка ошибок:
   - Если клик не удался или страница изменилась, вызови `wait` на 2-3 секунды или снова исследуй разметку через `query_dom`.
   - Если появилось всплывающее окно (баннер, выбор региона, cookie-нотис), найди кнопку закрытия через `query_dom` и нажми её.
3. Безопасность:
   - Для действий с оплатой, списанием средств или оформлением заказа всегда указывай понятное описание в поле `description` инструмента `click_element`, чтобы сработал Security Layer.
4. Завершение:
   - Когда цель достигнута (например, товар добавлен в корзину или найдены нужные данные), обязательно вызови инструмент `finish_task` с подробным итогом.
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
        """Запускает автономный цикл решения задачи с защитой от лимитов и зацикливания."""
        self.messages.append({"role": "user", "content": user_goal})
        console.print(Panel(f"[bold green]Новая задача:[/bold green] {user_goal}", title="Browser Agent"))

        step = 0
        while step < self.max_steps:
            step += 1

            # Троттлинг: пауза между шагами для соблюдения лимитов RPM
            time.sleep(2.0)

            response = None
            # Retry loop на случай превышения лимитов запросов (HTTP 429)
            response = None
            max_retries = 3
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
                    wait_sec = 15
                    console.print(f"[yellow]Лимит запросов (429). Ждём {wait_sec} сек... (попытка {attempt + 1}/{max_retries})[/yellow]")
                    time.sleep(wait_sec)
                except Exception as e:
                    # Если это временная перегрузка серверов 503 или сбой сети — ждём и повторяем
                    if attempt < max_retries - 1:
                        wait_sec = 5
                        console.print(f"[yellow]Сервер временно перегружен (503/сеть). Повтор через {wait_sec} сек... (попытка {attempt + 1}/{max_retries})[/yellow]")
                        time.sleep(wait_sec)
                    else:
                        console.print(f"[bold red]Не удалось связаться с LLM API после {max_retries} попыток:[/bold red] {e!s}")
                        return

            if not response:
                console.print("[bold red]Не удалось получить ответ от API после повторных попыток.[/bold red]")
                break

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # Добавляем ответ модели в историю сообщений
            self.messages.append(response_message.model_dump(exclude_none=True))

            # Логируем текстовые рассуждения модели, если они есть
            if response_message.content:
                console.print(f"\n[bold blue]Assistant:[/bold blue] {response_message.content}")

            # Если модель не вызвала тулы и закончила мысль
            if not tool_calls:
                console.print("\n[yellow]Агент завершил шаги без вызова инструментов.[/yellow]")
                break

            # Выполнение вызванных инструментов
            for tool_call in tool_calls:
                func = getattr(tool_call, "function", None)
                if not func:
                    continue

                function_name = func.name
                arguments_raw = func.arguments

                try:
                    arguments = json.loads(arguments_raw) if isinstance(arguments_raw, str) else arguments_raw
                except Exception:
                    arguments = {}

                # Структурированное логирование шага
                console.print(f"\n[cyan]🛠️  Using tool:[/cyan] [bold]{function_name}[/bold]")
                console.print(f"[dim]Input:[/dim] {json.dumps(arguments, ensure_ascii=False, indent=2)}")

                # Исполнение инструмента
                result = self.executor.execute(function_name, arguments)
                console.print(f"[green]Result:[/green] {result}")

                # Передача результата выполнения инструмента обратно модели
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })

                # Завершение при вызове финального инструмента
                if function_name == "finish_task":
                    summary = arguments.get("summary", "Задача успешно завершена.")
                    console.print(Panel(f"[bold green]Задача успешно выполнена![/bold green]\n\n{summary}", title="Отчёт агента"))
                    return

            # Проверка лимита шагов с возможностью интерактивного продления
            if step >= self.max_steps:
                console.print(f"\n[bold yellow]Достигнут лимит шагов ({self.max_steps}). Задача еще не завершена.[/bold yellow]")
                choice = input("Добавить еще 15 шагов для продолжения выполнения? (y/n): ").strip().lower()
                if choice in ["y", "yes", "да"]:
                    self.max_steps += 15
                    continue
                else:
                    console.print("[bold red]Выполнение остановлено пользователем.[/bold red]")
                    break
