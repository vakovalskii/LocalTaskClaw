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
        "name": "News Analyst",
        "emoji": "📰",
        "color": "#3b82f6",
        "role": "worker",
        "system_prompt": (
            "<role>You are a news analyst.</role>\n"
            "<instructions>\n"
            "Your job: find current news on a given topic (use search_web), "
            "read 2-3 sources (fetch_page), and compile a short digest "
            "(3-5 bullet points with source links).\n"
            "Save the result via write_file to the artifacts/ folder "
            "using the filename from the task.\n"
            "Be specific and to the point — no placeholders.\n"
            "</instructions>"
        ),
    },
    {
        "name": "Web Researcher",
        "emoji": "🔍",
        "color": "#8b5cf6",
        "role": "worker",
        "system_prompt": (
            "<role>You are a web researcher.</role>\n"
            "<instructions>\n"
            "You receive a topic or question, search for information via search_web "
            "and fetch_page (read actual page content), then write a structured report: "
            "what you found, key facts, comparison, conclusion.\n"
            "Save the result via write_file to artifacts/.\n"
            "Do not fabricate data — only use what you actually found online.\n"
            "</instructions>"
        ),
    },
    {
        "name": "Code Reviewer",
        "emoji": "🧑‍💻",
        "color": "#10b981",
        "role": "worker",
        "system_prompt": (
            "<role>You are a code reviewer and workspace analyst.</role>\n"
            "<instructions>\n"
            "Use list_files to survey the structure, read_file to read specific files.\n"
            "Write a review: what is good, what is bad, specific improvement suggestions "
            "with examples.\n"
            "Save the report via write_file to artifacts/.\n"
            "Evaluate objectively, provide practical recommendations.\n"
            "</instructions>"
        ),
    },
    {
        "name": "Writer",
        "emoji": "✍️",
        "color": "#f59e0b",
        "role": "worker",
        "system_prompt": (
            "<role>You are an AI writer and content creator.</role>\n"
            "<instructions>\n"
            "You write texts on a given topic: articles, essays, descriptions, plans, scripts.\n"
            "Use search_web for current context when needed.\n"
            "Write in a lively, structured style.\n"
            "Save the result via write_file to artifacts/.\n"
            "</instructions>"
        ),
    },
]

ORCHESTRATOR_AGENT = {
    "name": "Chief Orchestrator",
    "emoji": "🎯",
    "color": "#ef4444",
    "role": "orchestrator",
    "system_prompt": (
        "<role>You are the chief orchestrator of an AI agent team. "
        "You manage the kanban board and coordinate workers.</role>\n\n"
        "<algorithm>\n"
        "<step name=\"dispatch\">\n"
        "Call kanban_list. "
        "Find tasks in the backlog column that have an assigned agent. "
        "EXCLUDE your own task (the one currently running) from dispatch. "
        "For each eligible task, call kanban_run(task_id). "
        "Do NOT use kanban_move — only kanban_run launches an agent.\n"
        "</step>\n\n"
        "<step name=\"verify\">\n"
        "Find tasks in the review column. "
        "For each one: call kanban_read_result(task_id). "
        "APPROVE (approved=true) if the artifact contains any text (non-empty). "
        "REJECT (approved=false) ONLY if there is an error or empty file. "
        "Do not be a perfectionist — any result is better than a retry.\n"
        "</step>\n\n"
        "<step name=\"report\">\n"
        "Call kanban_report with a summary and a list of all processed tasks.\n"
        "IMPORTANT: use correct statuses in results:\n"
        "- 'started' — if you launched the task via kanban_run\n"
        "- 'done' — if the task was verified and approved\n"
        "- 'failed' — if the task failed or the artifact is empty\n"
        "- 'skipped' — if you skipped the task\n"
        "Do not write arbitrary text in status — only these values.\n"
        "</step>\n"
        "</algorithm>\n\n"
        "<stop_rules>\n"
        "- Do not touch tasks in the in_progress and done columns\n"
        "- Do not launch your own task via kanban_run\n"
        "- Do not use kanban_move to move worker tasks\n"
        "</stop_rules>"
    ),
}

# ── Task definitions ──────────────────────────────────────────────────────────

TASKS = [
    {
        "title": "AI News Digest",
        "description": (
            "Find the 5 most interesting news stories about AI, LLMs, and AI agents from the past week. "
            "For each: headline, gist in 2 sentences, link to the source. "
            "Save to artifacts/ai_news_digest.md"
        ),
        "agent": "News Analyst",
        "column": "backlog",
    },
    {
        "title": "Top Open-Source LLMs for Local Deployment",
        "description": (
            "Research which open-source LLM models are currently the best for running on local hardware. "
            "Criteria: answer quality, model size (GB), VRAM requirements, license. "
            "Create a comparison table of the top 5 models of 2025. "
            "Save to artifacts/top_local_llm.md"
        ),
        "agent": "Web Researcher",
        "column": "backlog",
    },
    {
        "title": "Workspace Structure Review",
        "description": (
            "Examine the file structure of the workspace: use list_files. "
            "Write a report: what exists, how it is organized, what can be improved. "
            "Propose a folder organization scheme. "
            "Save to artifacts/workspace_review.md"
        ),
        "agent": "Code Reviewer",
        "column": "backlog",
    },
    {
        "title": "Essay: AI Agents in 2027",
        "description": (
            "Write a 400-600 word essay: 'How AI Agents Will Change Everyday Life by 2027'. "
            "Base it on real trends (use search_web for context). "
            "Structure: introduction, 3 specific examples, conclusion. "
            "Save to artifacts/ai_agents_2027.md"
        ),
        "agent": "Writer",
        "column": "backlog",
    },
    {
        "title": "Comparison: Claude vs GPT-4 vs Gemini",
        "description": (
            "Research the current state of three top LLMs: Claude, GPT-4o, Gemini 1.5 Pro. "
            "Compare by: reasoning quality, API cost, context window, unique features. "
            "Write an honest comparison with recommendations for different use cases. "
            "Save to artifacts/llm_comparison.md"
        ),
        "agent": "Web Researcher",
        "column": "backlog",
    },
]

ORCHESTRATOR_TASK = {
    "title": "Orchestration Cycle",
    "description": (
        "Run a full orchestration cycle: "
        "check backlog -> launch agents -> verify results -> send report. "
        "Runs automatically every 5 minutes."
    ),
    "agent": "Chief Orchestrator",
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
    print(f"  AGENTS ({len(agents)})")
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
    print(f"  KANBAN ({len(tasks)} tasks)")
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
            agent = f"→ {t['agent_emoji']} {t['agent_name']}" if t.get("agent_name") else "→ (no agent)"
            repeat = f" ♻ {t['repeat_minutes']}m" if t.get("repeat_minutes") else ""
            status = f" [{t['status']}]" if t["status"] not in ("idle", "done") else ""
            print(f"    #{t['id']} {t['title']} {agent}{repeat}{status}")
    print()


# ── Reset ─────────────────────────────────────────────────────────────────────

def reset_all():
    print("⚠️  Deleting all existing tasks and agents...")

    tasks = get("/kanban")["tasks"]
    for t in tasks:
        try:
            delete(f"/kanban/tasks/{t['id']}")
        except Exception as e:
            print(f"  Error deleting task #{t['id']}: {e}")

    agents = get("/agents")["agents"]
    for a in agents:
        try:
            delete(f"/agents/{a['id']}")
        except Exception as e:
            print(f"  Error deleting agent #{a['id']}: {e}")

    print(f"  Deleted: {len(tasks)} tasks, {len(agents)} agents")


# ── Seed ──────────────────────────────────────────────────────────────────────

def seed():
    existing_agents = _agents_by_name()
    existing_tasks = _tasks_by_title()
    agent_map: dict[str, dict] = {}

    # Create workers
    print("\n🤖 Creating agents...")
    for spec in WORKER_AGENTS:
        if spec["name"] in existing_agents:
            agent = existing_agents[spec["name"]]
            print(f"  ↩ #{agent['id']} {spec['emoji']} {spec['name']} — already exists")
        else:
            agent = post("/agents", spec)
            print(f"  ✓ #{agent['id']} {spec['emoji']} {spec['name']}")
        agent_map[spec["name"]] = agent

    # Create orchestrator
    if ORCHESTRATOR_AGENT["name"] in existing_agents:
        orc_agent = existing_agents[ORCHESTRATOR_AGENT["name"]]
        print(f"  ↩ #{orc_agent['id']} {ORCHESTRATOR_AGENT['emoji']} {ORCHESTRATOR_AGENT['name']} — already exists")
    else:
        orc_agent = post("/agents", ORCHESTRATOR_AGENT)
        print(f"  ✓ #{orc_agent['id']} {ORCHESTRATOR_AGENT['emoji']} {ORCHESTRATOR_AGENT['name']} [orchestrator]")
    agent_map[ORCHESTRATOR_AGENT["name"]] = orc_agent

    # Create worker tasks
    print("\n📋 Creating tasks...")
    for spec in TASKS:
        if spec["title"] in existing_tasks:
            t = existing_tasks[spec["title"]]
            print(f"  ↩ #{t['id']} {spec['title']} — already exists")
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
        print(f"  ↩ #{ot['id']} {ORCHESTRATOR_TASK['title']} ♻ {ot.get('repeat_minutes', 0)}m — already exists")
    else:
        ot = post("/kanban/tasks", {
            "title": ORCHESTRATOR_TASK["title"],
            "description": ORCHESTRATOR_TASK["description"],
            "agent_id": orc_agent["id"],
            "column": ORCHESTRATOR_TASK["column"],
            "repeat_minutes": ORCHESTRATOR_TASK["repeat_minutes"],
        })
        print(f"  ✓ #{ot['id']} {ORCHESTRATOR_TASK['title']} ♻ {ORCHESTRATOR_TASK['repeat_minutes']}m → 🎯 {ORCHESTRATOR_AGENT['name']}")

    print(f"\n✅ Done! Launch the orchestrator manually via UI or:")
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
        print(f"❌ API unavailable: {e}")
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
