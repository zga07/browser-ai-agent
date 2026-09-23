import json
import os
import time
from typing import Any, cast

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.text import Text

from tools import TOOLS_SCHEMA, ToolExecutor

load_dotenv()
console = Console()

SYSTEM_PROMPT = """
Ты — элитный автономный агент управления браузером. Твоя цель — надежно, точно и результативно выполнять пользовательские задачи в интерфейсах.

ТЫ ВЗАИМОДЕЙСТВУЕШЬ С СИСТЕМОЙ ЧЕРЕЗ:
- Числовые индексы элементов [ID], полученные строго через `query_dom`.
- Координатные клики и физический ввод Playwright.

СТРОГИЙ ЦИКЛ РАБОТЫ (THINK -> ACT -> OBSERVE):
Перед КАЖДЫМ вызовом инструмента ты обязан выдать краткий анализ:
1. НАБЛЮДЕНИЕ (Observation): Что видно на экране? Какой фактический результат прошлого шага?
2. АНАЛИЗ (Reasoning): Достигнута ли текущая подцель? Добавлен ли товар (есть ли счетчик/изменилась корзина)?
3. ПЛАН (Plan): Какое ОДНО следующее действие? Если только что был клик или wait — ПЛАН ВСЕГДА: вызвать `query_dom`.

КРИТИЧЕСКИЕ ПРАВИЛА И ПАТТЕРНЫ:

1. СИНХРОНИЗАЦИЯ РАЗМЕТКИ (ЗАПРЕТ НА СЛЕПЫЕ ДЕЙСТВИЯ):
   - После КАЖДОГО клика, перехода или инструмента `wait` кэш устаревает.
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО кликать или вводить текст дважды подряд без промежуточного вызова `query_dom`!
   - Любое действие должно опираться ТОЛЬКО на список ID из самого последнего `query_dom`.

2. ИНТЕРНЕТ-МАГАЗИНЫ И КОРЗИНА (Лавка, Еда, маркетплейсы):
   - Различай просмотр и покупку:
     * Ссылка с названием товара (тег 'a') НЕ кладет товар в корзину, а открывает карточку товара!
     * Чтобы товар попал в корзину, нажми именно кнопку добавления: «+ (Добавить)», «В корзину», кнопку с ценой на карточке товара.
     * Если клик открыл всплывающую карточку товара — найди внутри нее кнопку «В корзину» / «Добавить» и нажми её.
   - Правило «Один товар — полный цикл»:
     Если нужно добавить несколько товаров (например, Колу И Воду):
     1) Нашел товар №1 -> нажал кнопку добавления в корзину («В корзину» / «+»).
     2) Вызови `query_dom` и ОБЯЗАТЕЛЬНО убедись, что товар добавлен (кнопка превратилась в счетчик «- 1 +» или обновилась кнопка корзины).
     3) ТОЛЬКО ПОСЛЕ ЭТОГО стирай строку поиска и ищи товар №2! Запрещено искать второй товар, не положив первый.
   - Проверка корзины перед финишем:
     * Перед вызовом `finish_task` нажми кнопку «Корзина» / «В корзину · XXX ₽».
     * Открой страницу корзины, вызови `query_dom` и прочитай РЕАЛЬНЫЕ названия товаров из списка.
     * В `completed_items` заноси ТОЛЬКО те товары, которые реально лежат в корзине на экране.

3. ОТКЛИКИ НА ВАКАНСИИ И ФОРМЫ (hh.ru и др.):
   - В разделе «Резюме и профиль» находятся твои резюме. Прочитай стек, но не откликайся на собственное резюме!
   - Поиск вакансий веди через строку поиска на главной или странице поиска.
   - В модалке отклика: введи/сгенерируй сопроводительное письмо и нажми «Откликнуться». КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО нажимать «Отмена» или Escape во время процесса отклика!
   - Если после первого шага появился опросник или выбор резюме («Сохранить и продолжить») — подтверди выбор и заверши процесс.
   - После отправки отклика используй `go_back`, чтобы вернуться к списку вакансий.

4. РАБОТА С ПОЧТОЙ:
   - Спам: рекламные купоны, холодные рассылки, сомнительные предложения.
   - ЗАПРЕЩЕНО УДАЛЯТЬ: письма о вакансиях/стажировках, коды подтверждения, пароли, системные уведомления Google/Apple, квитанции и чеки.
   - Отмечай спам чекбоксами в списке и нажимай «Удалить» / «В спам» один раз для группы.

5. ЧЕСТНЫЙ СТРУКТУРИРОВАННЫЙ ФИНИШ:
   - В массиве `completed_items` инструмента `finish_task` указывай ТОЛЬКО реально выполненные действия.
   - Если просили два товара, а добавлен один — так прямо и укажи: 1 товар в `completed_items`, а в `final_comment` напиши, что второй не найден или не успел добавиться. Никаких выдуманных фактов!
"""


class BrowserAgent:
    def __init__(
        self,
        tool_executor: ToolExecutor,
        model: str | None = None,
        max_steps: int = 35
    ):
        self.executor = tool_executor
        self.model = model or os.getenv("MODEL_NAME", "gpt-4o-mini")
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
        console.print()
        console.print(Panel(
            Text(user_goal, style="bold white"),
            title="[bold green]Цель задачи[/bold green]",
            title_align="left",
            border_style="green",
            expand=False
        ))

        step = 0
        while step < self.max_steps:
            step += 1
            response = None
            max_retries = 3

            with console.status(f"[bold blue]Шаг {step}:[/bold blue] Запрос к модели...", spinner="dots"):
                for attempt in range(max_retries):
                    try:
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=cast(Any, self.messages),
                            tools=cast(Any, TOOLS_SCHEMA),
                            tool_choice="auto",
                            parallel_tool_calls=False
                        )
                        break
                    except RateLimitError:
                        time.sleep(10)
                    except Exception as e:
                        if attempt == max_retries - 1:
                            console.print(f"[bold red]Сбой LLM API:[/bold red] {e!s}")
                            return
                        time.sleep(3)

            if not response:
                console.print("[bold red]Пустой ответ от провайдера API.[/bold red]")
                break

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls
            self.messages.append(response_message.model_dump(exclude_none=True))

            if response_message.content:
                console.print(Panel(
                    response_message.content,
                    title="[bold dim]Мысли агента[/bold dim]",
                    title_align="left",
                    border_style="dim",
                    expand=False
                ))

            if not tool_calls:
                console.print("[dim]Агент завершил шаги без вызова действий.[/dim]")
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

                console.print(f"\n[cyan]▶ [bold]{function_name}[/bold][/cyan]")
                if arguments:
                    console.print(JSON.from_data(arguments))

                result = self.executor.execute(function_name, arguments)

                res_str = str(result)
                if "Интерактивные элементы" in res_str:
                    lines = res_str.splitlines()
                    preview = "\n".join(lines[:6]) + f"\n... [ещё {max(0, len(lines) - 6)} элементов скрыто]"
                    console.print(f"[dim green]Result:[/dim green]\n{preview}")
                else:
                    console.print(f"[dim green]Result:[/dim green] {res_str}")

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": res_str
                })

                # Оставляем развернутым только последний срез DOM в истории
                dom_count = 0
                for msg in reversed(self.messages):
                    if msg.get("role") == "tool" and "Интерактивные элементы" in str(msg.get("content", "")):
                        dom_count += 1
                        if dom_count > 1:
                            msg["content"] = "[Срез DOM обработан ранее]"

                if function_name == "finish_task":
                    items = arguments.get("completed_items", [])
                    final_comment = arguments.get("final_comment", "Задача завершена.")

                    report_lines = []
                    if items:
                        report_lines.append("[bold underline]Выполненные действия:[/bold underline]\n")
                        for idx, item in enumerate(items, 1):
                            title = item.get("title", "—")
                            details = item.get("details", "—")
                            status = item.get("result_status", "—")
                            report_lines.append(f"  [bold cyan]{idx}. {title}[/bold cyan]")
                            report_lines.append(f"     • [dim]Детали:[/dim] {details}")
                            report_lines.append(f"     • [dim]Статус:[/dim] [green]{status}[/green]\n")

                    report_lines.append(f"[bold]Итог:[/bold] {final_comment}")
                    full_report = "\n".join(report_lines)

                    console.print()
                    console.print(Panel(
                        full_report,
                        title="[bold green]✓ Результат выполнения[/bold green]",
                        title_align="left",
                        border_style="green",
                        padding=(1, 2)
                    ))
                    return

            if step >= self.max_steps:
                console.print(f"\n[yellow]Достигнут лимит шагов ({self.max_steps}).[/yellow]")
                choice = console.input("Продлить выполнение на 15 шагов? (y/n): ").strip().lower()
                if choice in ["y", "yes", "да"]:
                    self.max_steps += 15
                    continue
                break
