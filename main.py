from rich.console import Console

from agent import BrowserAgent
from browser_engine import BrowserEngine
from dom_processor import DOMProcessor
from tools import ToolExecutor

console = Console()


def main():
    console.print("[bold cyan]═══════════════════════════════════════════════[/bold cyan]")
    console.print("[bold green]        AI Autonomous Browser Agent            [/bold green]")
    console.print("[bold cyan]═══════════════════════════════════════════════[/bold cyan]")
    console.print("[dim]Запуск браузера и подготовка рабочего профиля...[/dim]\n")

    browser = BrowserEngine(user_data_dir="./browser_profile")
    dom_processor = DOMProcessor()
    executor = ToolExecutor(browser=browser, dom_processor=dom_processor)
    agent = BrowserAgent(tool_executor=executor)

    console.print("[bold yellow]Браузер готов к работе![/bold yellow]")
    console.print("Введи задачу для агента (или 'exit' для выхода).\n")

    try:
        while True:
            user_input = input("Задача > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "выход"]:
                break

            agent.run(user_input)
            console.print("\n[dim]Готов к следующей задаче.[/dim]\n")

    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем.[/yellow]")
    finally:
        console.print("\n[dim]Закрытие браузера...[/dim]")
        browser.close()
        console.print("[green]Сессия сохранена. Завершение работы.[/green]")


if __name__ == "__main__":
    main()
