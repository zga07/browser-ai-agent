# AI Autonomous Browser Agent

Автономный веб-агент на базе **Playwright** и **LLM Tool Calling** для выполнения многошаговых задач в браузере.

---

## Особенности

* **Set-of-Mark (DOM Grounding):** Динамическая разметка интерактивных элементов индексами `[ID]` и клики по физическим экранным координатам.
* **Строгий ReAct-цикл:** Обязательный шаг рассуждения (`Observation → Reasoning → Plan`) перед каждым действием.
* **Security Layer:** Запрос подтверждения в терминале перед критическими/финансовыми действиями (оплата, удаление).
* **Single-tab режим:** Принудительное открытие всех ссылок в текущей вкладке без пложения фоновых окон.
* **Persistent Session:** Сохранение профиля Chromium (авторизации и куки не слетают между запусками).

---

## 📁 Структура проекта

```text
├── main.py              # CLI-интерфейс на Rich и цикл задач
├── agent.py             # ReAct-оркестратор и системный промпт
├── browser_engine.py    # Playwright-рантайм, клики, ввод, скролл
├── dom_processor.py     # JS-сканер Set-of-Mark и фильтрация DOM
├── tools.py             # Схема инструментов LLM и Security Layer
└── browser_profile/     # Сохраненная сессия браузера
```

---

## Старт проекта

### 1. Установка

```bash
git clone [https://github.com/zga/browser-ai-agent.git](https://github.com/zga/browser-ai-agent.git)
cd browser-ai-agent

python3 -m venv venv
source venv/bin/activate

pip install playwright openai python-dotenv rich
playwright install chromium
```

### 2. Настройка `.env`

```env
OPENAI_API_KEY="your-api-key"
OPENAI_BASE_URL="[https://api.openai.com/v1](https://api.openai.com/v1)"
MODEL_NAME="gpt-4o-mini"
```

### 3. Запуск

```bash
python main.py
```

---
