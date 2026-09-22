import os
import json
from typing import Any, List, cast
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from dotenv import load_dotenv

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
   - Для действий с оплатой, списанием средств или удалением данных всегда указывай понятное описание в поле `description` инструмента `click_element`, чтобы сработал Security Layer.
4. Завершение:
   - Когда цель достигнута (например, товар добавлен в корзину или найдены нужные данные), обязательно вызови инструмент `finish_task` с подробным итогом.
"""


class BrowserAgent:
    def __init__(
        self,
        tool_executor: ToolExecutor,
        model: str | None = None,
        max_steps: int = 25
    ):
        self.executor = tool_executor
        self.model = model or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.max_steps = max_steps
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        self.messages: List[Any] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def run(self, user_goal: str):
        """Запускает автономный цикл решения задачи."""
        self.messages.append({"role": "user", "content": user_goal})
        console.print(Panel(f"[bold green]Новая задача:[/bold green] {user_goal}", title="Browser Agent"))

        step = 0
        while step < self.max_steps:
            step += 1

            try:
                # 1. Запрос к LLM с передачей истории и схемы инструментов
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=cast(Any, self.messages),
                    tools=cast(Any, TOOLS_SCHEMA),
                    tool_choice="auto"
                )
            except Exception as e:
                console.print(f"[bold red]Ошибка обращения к LLM API:[/bold red] {str(e)}")
                break

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # Добавляем ответ модели в историю в виде чистого словаря
            self.messages.append(response_message.model_dump(exclude_none=True))

            # 2. Если модель вывела обычный текст — логируем его
            if response_message.content:
                console.print(f"\n[bold blue]Assistant:[/bold blue] {response_message.content}")

            # 3. Если модель не вызывала тулы и завершила мысль
            if not tool_calls:
                console.print("\n[yellow]Агент завершил шаги без вызова инструментов.[/yellow]")
                break

            # 4. Выполнение вызванных инструментов
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

                # Красивый структурированный вывод вызова тула
                console.print(f"\n[cyan]🛠️  Using tool:[/cyan] [bold]{function_name}[/bold]")
                console.print(f"[dim]Input:[/dim] {json.dumps(arguments, ensure_ascii=False, indent=2)}")

                # Вызов инструмента через исполнитель
                result = self.executor.execute(function_name, arguments)
                console.print(f"[green]Result:[/green] {result}")

                # Запись результата тула обратно в контекст диалога
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })

                # Если вызвана финальная функция завершения
                if function_name == "finish_task":
                    summary = arguments.get("summary", "Задача завершена.")
                    console.print(Panel(f"[bold green]Задача успешно выполнена![/bold green]\n\n{summary}", title="Отчёт агента"))
                    return

        if step >= self.max_steps:
            console.print("[bold red]Достигнут лимит шагов (max_steps). Выполнение остановлено.[/bold red]")
