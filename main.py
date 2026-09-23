from rich.console import Console

from agent import BrowserAgent
from browser_engine import BrowserEngine
from dom_processor import DOMProcessor
from tools import ToolExecutor

console = Console()


def main():
    console.clear()
    console.rule("[bold cyan]AI Autonomous Browser Agent[/bold cyan]")
    console.print("[dim]Инициализация сессии Chromium и компонентов...[/dim]", justify="center")

    browser = BrowserEngine(user_data_dir="./browser_profile")
    dom_processor = DOMProcessor()
    executor = ToolExecutor(browser=browser, dom_processor=dom_processor)
    agent = BrowserAgent(tool_executor=executor)

    console.rule(style="dim")
    console.print("[bold green]●[/bold green] Браузер запущен и готов к задачам.")
    console.print("[dim]Для выхода введи 'exit' или нажми Ctrl+C[/dim]\n")

    try:
        while True:
            user_input = console.input("[bold cyan]Задача[/bold cyan] [dim]>[/dim] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "выход"]:
                break

            agent.run(user_input)
            console.print()
            console.rule(style="dim")

    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем.[/yellow]")
    finally:
        with console.status("[dim]Корректное сохранение профиля и закрытие...[/dim]"):
            browser.close()
        console.print("[bold green]✓[/bold green] Сессия сохранена.")


if __name__ == "__main__":
    main()
