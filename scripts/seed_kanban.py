#!/usr/bin/env python3
"""
Seed the kanban board with demo agents and tasks.

Creates 4 specialist workers + 1 orchestrator that auto-runs every 5 minutes.
The orchestrator dispatches workers, verifies results, sends Telegram report.

Usage:
    cd /Users/v.kovalskii/LocalTaskClaw
    python scripts/seed_kanban.py           # add agents/tasks (skip if already exists)
    python scripts/seed_kanban.py --reset   # wipe all existing, then seed fresh
    python scripts/seed_kanban.py --status  # just print current board state
"""

import argparse
import os
import sys
import httpx

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("API_URL", "http://localhost:11387")


def _get_secret():
    # Try multiple locations for core.env
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "secrets", "core.env"),
        os.path.expanduser("~/.localtaskclaw/app/secrets/core.env"),
    ]
    for env_file in candidates:
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("API_SECRET="):
                        return line.split("=", 1)[1].strip()
        except FileNotFoundError:
            continue
    return os.environ.get("API_SECRET", "")


API_SECRET = _get_secret()
HEADERS = (
    {"X-Api-Key": API_SECRET, "Content-Type": "application/json"}
    if API_SECRET
    else {"Content-Type": "application/json"}
)


def get(path):
    r = httpx.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def post(path, data):
    r = httpx.post(f"{BASE_URL}{path}", json=data, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def patch(path, data):
    r = httpx.patch(f"{BASE_URL}{path}", json=data, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def delete(path):
    r = httpx.delete(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()


# ── Agent definitions ─────────────────────────────────────────────────────────

WORKER_AGENTS = [
    {
        "name": "Новостной аналитик",
        "emoji": "📰",
        "color": "#3b82f6",
        "role": "worker",
        "system_prompt": (
            "Ты — новостной аналитик. Твоя работа: искать актуальные новости по заданной теме "
            "(используй search_web), читать 2-3 источника (fetch_page), "
            "составить краткий дайджест на русском языке (3-5 пунктов с источниками). "
            "Сохрани результат через write_file в папку artifacts/ с именем из задачи. "
            "Пиши конкретно и по делу — никаких заглушек."
        ),
    },
    {
        "name": "Веб-исследователь",
        "emoji": "🔍",
        "color": "#8b5cf6",
        "role": "worker",
        "system_prompt": (
            "Ты — веб-исследователь. Получаешь тему или вопрос, "
            "ищешь информацию через search_web и fetch_page (читай реальный контент страниц), "
            "пишешь структурированный отчёт на русском: что нашёл, главные факты, сравнение, вывод. "
            "Сохраняй результат через write_file в artifacts/. "
            "Не придумывай данные — только то, что реально нашёл в сети."
        ),
    },
    {
        "name": "Ревьювер кода",
        "emoji": "🧑‍💻",
        "color": "#10b981",
        "role": "worker",
        "system_prompt": (
            "Ты — code reviewer и аналитик рабочего пространства. "
            "Используй list_files для обзора структуры, read_file для чтения конкретных файлов. "
            "Пиши review: что хорошо, что плохо, конкретные предложения по улучшению с примерами. "
            "Сохраняй отчёт через write_file в artifacts/. "
            "Оценивай объективно, давай практические рекомендации."
        ),
    },
    {
        "name": "Писатель",
        "emoji": "✍️",
        "color": "#f59e0b",
        "role": "worker",
        "system_prompt": (
            "Ты — AI-писатель и контент-мейкер. Пишешь тексты по заданной теме: "
            "статьи, эссе, описания, планы, сценарии. "
            "При необходимости используй search_web для актуального контекста. "
            "Пиши на русском, живым языком, структурированно. "
            "Сохраняй результат через write_file в artifacts/."
        ),
    },
]

ORCHESTRATOR_AGENT = {
    "name": "Главный оркестратор",
    "emoji": "🎯",
    "color": "#ef4444",
    "role": "orchestrator",
    "system_prompt": (
        "Ты — главный оркестратор команды AI-агентов. "
        "Управляешь канбан-доской и координируешь работников.\n\n"
        "АЛГОРИТМ каждого цикла:\n\n"
        "## ШАГ 1 — ЗАПУСК\n"
        "Вызови kanban_list. "
        "Найди задачи в колонке backlog у которых есть назначенный агент (→ в списке написан агент). "
        "ИСКЛЮЧИ из запуска свою собственную задачу (ту, которая сейчас running). "
        "Для каждой подходящей задачи вызови kanban_run(task_id). "
        "НЕ используй kanban_move — только kanban_run запускает агента.\n\n"
        "## ШАГ 2 — ВЕРИФИКАЦИЯ\n"
        "Найди задачи в колонке review. "
        "Для каждой: вызови kanban_read_result(task_id). "
        "ОДОБРЯЙ (approved=true) если артефакт содержит хоть какой-то текст (не пустой). "
        "ОТКЛОНЯЙ (approved=false) ТОЛЬКО если ошибка или пустой файл. "
        "Не будь перфекционистом — любой результат лучше повтора.\n\n"
        "## ШАГ 3 — ОТЧЁТ\n"
        "Вызови kanban_report с summary и списком всех обработанных задач.\n"
        "ВАЖНО: используй правильные статусы в results:\n"
        "- 'started' — если ты запустил задачу через kanban_run\n"
        "- 'done' — если задача была верифицирована и одобрена\n"
        "- 'failed' — если задача провалена или артефакт пуст\n"
        "- 'skipped' — если задачу пропустил\n"
        "Не пиши произвольный текст в status — только эти значения.\n\n"
        "СТОП-ПРАВИЛА:\n"
        "- Не трогай задачи в колонке in_progress и done\n"
        "- Не запускай свою собственную задачу через kanban_run\n"
        "- Не используй kanban_move для перемещения задач воркеров"
    ),
}

# ── Task definitions ──────────────────────────────────────────────────────────

TASKS = [
    {
        "title": "Дайджест новостей по AI",
        "description": (
            "Найди 5 самых интересных новостей про AI, LLM и AI-агентов за последнюю неделю. "
            "Для каждой: заголовок, суть в 2 предложениях, ссылка на источник. "
            "Сохрани в artifacts/ai_news_digest.md"
        ),
        "agent": "Новостной аналитик",
        "column": "backlog",
    },
    {
        "title": "Топ open-source LLM для локального запуска",
        "description": (
            "Исследуй какие open-source LLM модели сейчас лучшие для запуска на своём железе. "
            "Критерии: качество ответов, размер модели (GB), требования к VRAM, лицензия. "
            "Сделай сравнительную таблицу топ-5 моделей 2025 года. "
            "Сохрани в artifacts/top_local_llm.md"
        ),
        "agent": "Веб-исследователь",
        "column": "backlog",
    },
    {
        "title": "Обзор структуры воркспейса",
        "description": (
            "Изучи структуру файлов в рабочем пространстве: используй list_files. "
            "Напиши отчёт: что есть, как организовано, что можно улучшить. "
            "Предложи схему организации папок. "
            "Сохрани в artifacts/workspace_review.md"
        ),
        "agent": "Ревьювер кода",
        "column": "backlog",
    },
    {
        "title": "Эссе: AI-агенты в 2027 году",
        "description": (
            "Напиши эссе на 400-600 слов: 'Как AI-агенты изменят повседневную жизнь к 2027 году'. "
            "Опирайся на реальные тренды (используй search_web для контекста). "
            "Структура: введение, 3 конкретных примера, вывод. "
            "Сохрани в artifacts/ai_agents_2027.md"
        ),
        "agent": "Писатель",
        "column": "backlog",
    },
    {
        "title": "Сравнение: Claude vs GPT-4 vs Gemini",
        "description": (
            "Исследуй текущее состояние трёх топовых LLM: Claude, GPT-4o, Gemini 1.5 Pro. "
            "Сравни по: качеству reasoning, стоимости API, контекстному окну, особенностям. "
            "Напиши честное сравнение с рекомендацией под разные задачи. "
            "Сохрани в artifacts/llm_comparison.md"
        ),
        "agent": "Веб-исследователь",
        "column": "backlog",
    },
]

ORCHESTRATOR_TASK = {
    "title": "Цикл оркестрации",
    "description": (
        "Запусти полный цикл оркестрации: "
        "проверь backlog → запусти агентов → верифицируй результаты → отправь отчёт. "
        "Работает автоматически каждые 5 минут."
    ),
    "agent": "Главный оркестратор",
    "column": "backlog",
    "repeat_minutes": 5,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _agents_by_name() -> dict[str, dict]:
    return {a["name"]: a for a in get("/agents")["agents"]}


def _tasks_by_title() -> dict[str, dict]:
    return {t["title"]: t for t in get("/kanban")["tasks"]}


def _print_board():
    tasks = get("/kanban")["tasks"]
    agents = get("/agents")["agents"]

    print(f"\n{'='*60}")
    print(f"  АГЕНТЫ ({len(agents)})")
    print(f"{'='*60}")
    for a in agents:
        role_badge = "[orchestrator]" if a.get("role") == "orchestrator" else "[worker]"
        print(f"  #{a['id']} {a['emoji']} {a['name']} {role_badge}")

    cols = ["backlog", "in_progress", "review", "done", "needs_human"]
    col_names = {
        "backlog": "BACKLOG",
        "in_progress": "IN PROGRESS",
        "review": "REVIEW",
        "done": "DONE",
        "needs_human": "NEEDS HUMAN",
    }
    print(f"\n{'='*60}")
    print(f"  КАНБАН ({len(tasks)} задач)")
    print(f"{'='*60}")
    grouped: dict[str, list] = {}
    for t in tasks:
        grouped.setdefault(t["column"], []).append(t)
    for col in cols:
        items = grouped.get(col, [])
        if not items:
            continue
        print(f"\n  [{col_names[col]}]")
        for t in items:
            agent = f"→ {t['agent_emoji']} {t['agent_name']}" if t.get("agent_name") else "→ (без агента)"
            repeat = f" ♻ {t['repeat_minutes']}m" if t.get("repeat_minutes") else ""
            status = f" [{t['status']}]" if t["status"] not in ("idle", "done") else ""
            print(f"    #{t['id']} {t['title']} {agent}{repeat}{status}")
    print()


# ── Reset ─────────────────────────────────────────────────────────────────────

def reset_all():
    print("⚠️  Удаляю все существующие задачи и агентов...")

    tasks = get("/kanban")["tasks"]
    for t in tasks:
        try:
            delete(f"/kanban/tasks/{t['id']}")
        except Exception as e:
            print(f"  Ошибка удаления задачи #{t['id']}: {e}")

    agents = get("/agents")["agents"]
    for a in agents:
        try:
            delete(f"/agents/{a['id']}")
        except Exception as e:
            print(f"  Ошибка удаления агента #{a['id']}: {e}")

    print(f"  Удалено: {len(tasks)} задач, {len(agents)} агентов")


# ── Seed ──────────────────────────────────────────────────────────────────────

def seed():
    existing_agents = _agents_by_name()
    existing_tasks = _tasks_by_title()
    agent_map: dict[str, dict] = {}

    # Create workers
    print("\n🤖 Создаю агентов...")
    for spec in WORKER_AGENTS:
        if spec["name"] in existing_agents:
            agent = existing_agents[spec["name"]]
            print(f"  ↩ #{agent['id']} {spec['emoji']} {spec['name']} — уже существует")
        else:
            agent = post("/agents", spec)
            print(f"  ✓ #{agent['id']} {spec['emoji']} {spec['name']}")
        agent_map[spec["name"]] = agent

    # Create orchestrator
    if ORCHESTRATOR_AGENT["name"] in existing_agents:
        orc_agent = existing_agents[ORCHESTRATOR_AGENT["name"]]
        print(f"  ↩ #{orc_agent['id']} {ORCHESTRATOR_AGENT['emoji']} {ORCHESTRATOR_AGENT['name']} — уже существует")
    else:
        orc_agent = post("/agents", ORCHESTRATOR_AGENT)
        print(f"  ✓ #{orc_agent['id']} {ORCHESTRATOR_AGENT['emoji']} {ORCHESTRATOR_AGENT['name']} [orchestrator]")
    agent_map[ORCHESTRATOR_AGENT["name"]] = orc_agent

    # Create worker tasks
    print("\n📋 Создаю задачи...")
    for spec in TASKS:
        if spec["title"] in existing_tasks:
            t = existing_tasks[spec["title"]]
            print(f"  ↩ #{t['id']} {spec['title']} — уже существует")
            continue
        agent = agent_map.get(spec["agent"])
        task_data = {
            "title": spec["title"],
            "description": spec["description"],
            "agent_id": agent["id"] if agent else None,
            "column": spec.get("column", "backlog"),
        }
        t = post("/kanban/tasks", task_data)
        print(f"  ✓ #{t['id']} {spec['title']} → {agent['emoji'] if agent else '?'} {spec['agent']}")

    # Create orchestrator task
    if ORCHESTRATOR_TASK["title"] in existing_tasks:
        ot = existing_tasks[ORCHESTRATOR_TASK["title"]]
        print(f"  ↩ #{ot['id']} {ORCHESTRATOR_TASK['title']} ♻ {ot.get('repeat_minutes', 0)}m — уже существует")
    else:
        ot = post("/kanban/tasks", {
            "title": ORCHESTRATOR_TASK["title"],
            "description": ORCHESTRATOR_TASK["description"],
            "agent_id": orc_agent["id"],
            "column": ORCHESTRATOR_TASK["column"],
            "repeat_minutes": ORCHESTRATOR_TASK["repeat_minutes"],
        })
        print(f"  ✓ #{ot['id']} {ORCHESTRATOR_TASK['title']} ♻ {ORCHESTRATOR_TASK['repeat_minutes']}m → 🎯 {ORCHESTRATOR_AGENT['name']}")

    print(f"\n✅ Готово! Запусти оркестратор вручную через UI или:")
    print(f"   curl -X POST {BASE_URL}/kanban/tasks/{ot['id']}/run -H 'X-Api-Key: {API_SECRET}'\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed kanban board with demo agents and tasks")
    parser.add_argument("--reset", action="store_true", help="Wipe all existing data before seeding")
    parser.add_argument("--status", action="store_true", help="Print current board state and exit")
    args = parser.parse_args()

    # Check API is up
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ API недоступен: {e}")
        sys.exit(1)

    if args.status:
        _print_board()
        return

    if args.reset:
        reset_all()

    seed()
    _print_board()


if __name__ == "__main__":
    main()
