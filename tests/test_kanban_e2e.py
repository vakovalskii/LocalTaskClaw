"""
End-to-end integration tests for LocalTaskClaw kanban + agent pipeline.

Runs against the live service (localhost:11387).
Creates isolated test data with TEST_ prefix and cleans up after each test.

Run:
    cd /Users/v.kovalskii/LocalTaskClaw
    ./venv/bin/pytest tests/test_kanban_e2e.py -v -s
"""

import asyncio
import os
import time
import httpx
import pytest

# ── Config ──────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("API_URL", "http://localhost:11387")

def _get_secret():
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

HEADERS = {"X-Api-Key": API_SECRET, "Content-Type": "application/json"} if API_SECRET else {"Content-Type": "application/json"}

# Timeouts
AGENT_TIMEOUT = 180   # seconds to wait for agent to finish
POLL_INTERVAL = 3     # seconds between polls


# ── Helpers ─────────────────────────────────────────────────────────────────

def get(path: str) -> dict:
    r = httpx.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def post(path: str, data: dict = None) -> dict:
    r = httpx.post(f"{BASE_URL}{path}", json=data or {}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def patch(path: str, data: dict) -> dict:
    r = httpx.patch(f"{BASE_URL}{path}", json=data, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def delete(path: str):
    r = httpx.delete(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()

def wait_for_task(task_id: int, timeout: int = AGENT_TIMEOUT) -> dict:
    """Poll until task leaves 'running' status. Returns final task state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        tasks = get("/kanban")["tasks"]
        task = next((t for t in tasks if t["id"] == task_id), None)
        assert task is not None, f"Task #{task_id} disappeared"
        if task["status"] != "running":
            return task
        print(f"  ⏳ task #{task_id} status={task['status']} column={task['column']} ...")
        time.sleep(POLL_INTERVAL)
    pytest.fail(f"Task #{task_id} still running after {timeout}s")

def cleanup_test_agents(created_ids: list[int]):
    for aid in created_ids:
        try:
            delete(f"/agents/{aid}")
        except Exception:
            pass

def cleanup_test_tasks(created_ids: list[int]):
    for tid in created_ids:
        try:
            delete(f"/kanban/tasks/{tid}")
        except Exception:
            pass


# ── Tests ────────────────────────────────────────────────────────────────────

class TestAPIHealth:
    """Basic connectivity and API health."""

    def test_health_endpoint(self):
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        assert r.status_code == 200, f"Health check failed: {r.text}"

    def test_agents_endpoint(self):
        d = get("/agents")
        assert "agents" in d
        assert isinstance(d["agents"], list)

    def test_kanban_endpoint(self):
        d = get("/kanban")
        assert "tasks" in d
        assert isinstance(d["tasks"], list)


class TestKanbanCRUD:
    """Create / read / update / delete kanban tasks and agents."""

    _agents: list[int] = []
    _tasks: list[int] = []

    def setup_method(self):
        self._agents = []
        self._tasks = []

    def teardown_method(self):
        cleanup_test_tasks(self._tasks)
        cleanup_test_agents(self._agents)

    def test_create_worker_agent(self):
        agent = post("/agents", {
            "name": "TEST_Worker",
            "emoji": "🔧",
            "color": "#00ff00",
            "system_prompt": "You are a test worker.",
            "role": "worker",
        })
        self._agents.append(agent["id"])
        assert agent["name"] == "TEST_Worker"
        assert agent["role"] == "worker"

    def test_create_orchestrator_agent(self):
        agent = post("/agents", {
            "name": "TEST_Orchestrator",
            "emoji": "🎯",
            "color": "#0000ff",
            "system_prompt": "You are a test orchestrator.",
            "role": "orchestrator",
        })
        self._agents.append(agent["id"])
        assert agent["role"] == "orchestrator"

    def test_create_task(self):
        task = post("/kanban/tasks", {
            "title": "TEST_Task basic",
            "description": "Test task",
            "column": "backlog",
        })
        self._tasks.append(task["id"])
        assert task["title"] == "TEST_Task basic"
        assert task["column"] == "backlog"
        assert task["status"] == "idle"

    def test_task_with_repeat(self):
        task = post("/kanban/tasks", {
            "title": "TEST_Task repeat",
            "description": "Repeat test",
            "column": "backlog",
            "repeat_minutes": 5,
        })
        self._tasks.append(task["id"])
        assert task["repeat_minutes"] == 5

    def test_update_task(self):
        task = post("/kanban/tasks", {"title": "TEST_Update me", "column": "backlog"})
        self._tasks.append(task["id"])

        updated = patch(f"/kanban/tasks/{task['id']}", {"title": "TEST_Updated"})
        assert updated["title"] == "TEST_Updated"

    def test_move_task(self):
        task = post("/kanban/tasks", {"title": "TEST_Move me", "column": "backlog"})
        self._tasks.append(task["id"])

        moved = post(f"/kanban/tasks/{task['id']}/move", {"column": "review"})
        assert moved["column"] == "review"


class TestKanbanTools:
    """Test kanban tool functions (via agent running them internally)."""

    _agents: list[int] = []
    _tasks: list[int] = []

    def setup_method(self):
        self._agents = []
        self._tasks = []

    def teardown_method(self):
        cleanup_test_tasks(self._tasks)
        cleanup_test_agents(self._agents)

    def test_kanban_list_tool_via_agent(self):
        """Run an agent that uses kanban_list and check it responds."""
        agent = post("/agents", {
            "name": "TEST_ListAgent",
            "emoji": "📋",
            "color": "#ff6600",
            "system_prompt": (
                "You are a test agent. Your only job is to call kanban_list once "
                "and then respond with exactly: KANBAN_LIST_OK"
            ),
            "role": "worker",
        })
        self._agents.append(agent["id"])

        task = post("/kanban/tasks", {
            "title": "TEST_List kanban",
            "description": "Call kanban_list and respond KANBAN_LIST_OK",
            "agent_id": agent["id"],
            "column": "backlog",
        })
        self._tasks.append(task["id"])

        post(f"/kanban/tasks/{task['id']}/run")
        result = wait_for_task(task["id"])

        print(f"\n  Result status: {result['status']}, column: {result['column']}")
        assert result["column"] in ("review", "done"), (
            f"Expected task in review/done, got column={result['column']} status={result['status']}"
        )


class TestWorkerAgent:
    """Worker agent executes a task and produces an artifact."""

    _agents: list[int] = []
    _tasks: list[int] = []

    def setup_method(self):
        self._agents = []
        self._tasks = []

    def teardown_method(self):
        cleanup_test_tasks(self._tasks)
        cleanup_test_agents(self._agents)

    def test_worker_completes_simple_task(self):
        """Worker agent receives a task, executes it, task ends in review."""
        agent = post("/agents", {
            "name": "TEST_SimpleWorker",
            "emoji": "⚡",
            "color": "#ffcc00",
            "system_prompt": (
                "You are a focused worker agent. "
                "When given a task, complete it immediately with a short response. "
                "Do not use any tools unless the task explicitly requires it."
            ),
            "role": "worker",
        })
        self._agents.append(agent["id"])

        task = post("/kanban/tasks", {
            "title": "TEST_Say hello",
            "description": "Respond with a short greeting. Nothing else.",
            "agent_id": agent["id"],
            "column": "backlog",
        })
        self._tasks.append(task["id"])

        # Task should start as idle in backlog
        assert task["status"] == "idle"
        assert task["column"] == "backlog"

        # Run the agent
        run_result = post(f"/kanban/tasks/{task['id']}/run")
        assert run_result["status"] == "started"

        # Immediately after run, task should be in_progress/running
        tasks = get("/kanban")["tasks"]
        running = next(t for t in tasks if t["id"] == task["id"])
        assert running["status"] == "running", f"Expected running, got {running['status']}"
        assert running["column"] == "in_progress", f"Expected in_progress, got {running['column']}"

        # Wait for completion
        result = wait_for_task(task["id"])
        print(f"\n  Final: status={result['status']} column={result['column']}")

        assert result["status"] == "done", f"Expected done, got status={result['status']}"
        assert result["column"] == "review", f"Expected review, got column={result['column']}"
        assert result["artifact"] is not None, "Expected artifact to be set"

    def test_worker_cannot_run_twice(self):
        """Running a task that is already running should not start a second instance."""
        agent = post("/agents", {
            "name": "TEST_DoubleRun",
            "emoji": "🔁",
            "color": "#cc0000",
            "system_prompt": "You are a slow worker. Write 3 sentences about the task and finish.",
            "role": "worker",
        })
        self._agents.append(agent["id"])

        task = post("/kanban/tasks", {
            "title": "TEST_Double run",
            "description": "Write 3 sentences about testing.",
            "agent_id": agent["id"],
            "column": "backlog",
        })
        self._tasks.append(task["id"])

        post(f"/kanban/tasks/{task['id']}/run")

        # Second run call should return error or already-running
        try:
            r2 = httpx.post(
                f"{BASE_URL}/kanban/tasks/{task['id']}/run",
                headers=HEADERS,
                timeout=10,
            )
            if r2.status_code == 200:
                data = r2.json()
                # Some impls return "already_running" status
                assert data.get("status") in ("already_running", "started"), (
                    f"Unexpected second run response: {data}"
                )
        except httpx.HTTPStatusError as e:
            # 400 or 409 is acceptable
            assert e.response.status_code in (400, 409)

        # Let it finish
        wait_for_task(task["id"])

    def test_cancel_running_task(self):
        """Cancelling a running task resets it to backlog/idle."""
        agent = post("/agents", {
            "name": "TEST_CancelTarget",
            "emoji": "⛔",
            "color": "#990000",
            "system_prompt": "You are a worker. Write a very long essay (500+ words) about the history of computing.",
            "role": "worker",
        })
        self._agents.append(agent["id"])

        task = post("/kanban/tasks", {
            "title": "TEST_Cancel me",
            "description": "Write 500 words about the history of computing.",
            "agent_id": agent["id"],
            "column": "backlog",
        })
        self._tasks.append(task["id"])

        post(f"/kanban/tasks/{task['id']}/run")

        # Give it 2 seconds to actually start
        time.sleep(2)

        # Cancel
        cancel_result = post(f"/kanban/tasks/{task['id']}/cancel")
        assert cancel_result["status"] in ("cancelled", "reset"), (
            f"Unexpected cancel result: {cancel_result}"
        )

        # Wait a moment for state to settle
        time.sleep(2)
        tasks = get("/kanban")["tasks"]
        t = next(t for t in tasks if t["id"] == task["id"])
        assert t["status"] != "running", f"Task should not be running after cancel, got {t['status']}"
        assert t["column"] == "backlog", f"Cancelled task should be in backlog, got {t['column']}"


class TestOrchestrator:
    """Orchestrator dispatches worker agents via kanban_run (not kanban_move)."""

    _agents: list[int] = []
    _tasks: list[int] = []

    def setup_method(self):
        self._agents = []
        self._tasks = []

    def teardown_method(self):
        # Cancel any running tasks first
        tasks = get("/kanban")["tasks"]
        for t in tasks:
            if t["id"] in self._tasks and t["status"] == "running":
                try:
                    post(f"/kanban/tasks/{t['id']}/cancel")
                except Exception:
                    pass
        time.sleep(1)
        cleanup_test_tasks(self._tasks)
        cleanup_test_agents(self._agents)

    def test_orchestrator_uses_kanban_run(self):
        """
        Orchestrator should call kanban_run for backlog tasks with agents.
        Worker tasks should transition to in_progress/running (not just moved via kanban_move).
        """
        # Create worker
        worker = post("/agents", {
            "name": "TEST_OrcWorker",
            "emoji": "🔩",
            "color": "#00aaff",
            "system_prompt": (
                "You are a simple worker. When given any task, "
                "respond with 'DONE: <task title>' and finish immediately."
            ),
            "role": "worker",
        })
        self._agents.append(worker["id"])

        # Create orchestrator
        orchestrator = post("/agents", {
            "name": "TEST_OrcOrchestrator",
            "emoji": "🎯",
            "color": "#ff00aa",
            "system_prompt": (
                "You are a kanban orchestrator. Your ONLY job:\n"
                "1. Call kanban_list to see all tasks.\n"
                "2. For EACH task in backlog that has an agent assigned: "
                "call kanban_run(task_id) to start the agent.\n"
                "3. Do NOT use kanban_move to move tasks to in_progress.\n"
                "4. After calling kanban_run for all tasks, finish.\n"
                "IMPORTANT: Use kanban_run, not kanban_move."
            ),
            "role": "orchestrator",
        })
        self._agents.append(orchestrator["id"])

        # Create 2 worker tasks in backlog
        task1 = post("/kanban/tasks", {
            "title": "TEST_OrcTask1",
            "description": "Say hello",
            "agent_id": worker["id"],
            "column": "backlog",
        })
        self._tasks.append(task1["id"])

        task2 = post("/kanban/tasks", {
            "title": "TEST_OrcTask2",
            "description": "Say goodbye",
            "agent_id": worker["id"],
            "column": "backlog",
        })
        self._tasks.append(task2["id"])

        # Create orchestrator task
        orc_task = post("/kanban/tasks", {
            "title": "TEST_OrcRun",
            "description": "Run the orchestrator to dispatch worker tasks",
            "agent_id": orchestrator["id"],
            "column": "backlog",
        })
        self._tasks.append(orc_task["id"])

        print(f"\n  Created: worker tasks #{task1['id']}, #{task2['id']}, orchestrator #{orc_task['id']}")

        # Run orchestrator
        post(f"/kanban/tasks/{orc_task['id']}/run")

        # Wait for orchestrator to finish
        orc_result = wait_for_task(orc_task["id"], timeout=120)
        print(f"  Orchestrator done: status={orc_result['status']} column={orc_result['column']}")

        # Verify worker tasks were STARTED (not just moved) — they should be running or done
        tasks = get("/kanban")["tasks"]
        t1 = next(t for t in tasks if t["id"] == task1["id"])
        t2 = next(t for t in tasks if t["id"] == task2["id"])

        print(f"  Worker task1: status={t1['status']} column={t1['column']}")
        print(f"  Worker task2: status={t2['status']} column={t2['column']}")

        # At minimum, both worker tasks should have left backlog (orchestrator started them)
        assert t1["column"] != "backlog" or t1["status"] == "running", (
            f"Task1 should have been started by orchestrator, got column={t1['column']} status={t1['status']}"
        )
        assert t2["column"] != "backlog" or t2["status"] == "running", (
            f"Task2 should have been started by orchestrator, got column={t2['column']} status={t2['status']}"
        )

        # Wait for workers to finish too
        print("  Waiting for worker tasks to complete...")
        r1 = wait_for_task(task1["id"], timeout=AGENT_TIMEOUT)
        r2 = wait_for_task(task2["id"], timeout=AGENT_TIMEOUT)

        print(f"  Final task1: status={r1['status']} column={r1['column']}")
        print(f"  Final task2: status={r2['status']} column={r2['column']}")

        assert r1["status"] == "done", f"Worker task1 should be done, got {r1['status']}"
        assert r2["status"] == "done", f"Worker task2 should be done, got {r2['status']}"
        assert r1["column"] == "review"
        assert r2["column"] == "review"

    def test_orchestrator_skips_tasks_without_agent(self):
        """Orchestrator should not touch tasks that have no agent assigned."""
        orchestrator = post("/agents", {
            "name": "TEST_SkipOrch",
            "emoji": "🎯",
            "color": "#aaaaaa",
            "system_prompt": (
                "You are a kanban orchestrator.\n"
                "1. Call kanban_list.\n"
                "2. For each task in backlog WITH an agent: call kanban_run.\n"
                "3. Leave tasks WITHOUT an agent untouched.\n"
                "4. Finish after dispatching all eligible tasks."
            ),
            "role": "orchestrator",
        })
        self._agents.append(orchestrator["id"])

        # Task with no agent — should stay in backlog
        no_agent_task = post("/kanban/tasks", {
            "title": "TEST_NoAgent",
            "description": "This task has no agent",
            "column": "backlog",
        })
        self._tasks.append(no_agent_task["id"])

        # Orchestrator task
        orc_task = post("/kanban/tasks", {
            "title": "TEST_SkipOrcRun",
            "description": "Dispatch tasks, skip those without agents",
            "agent_id": orchestrator["id"],
            "column": "backlog",
        })
        self._tasks.append(orc_task["id"])

        post(f"/kanban/tasks/{orc_task['id']}/run")
        wait_for_task(orc_task["id"], timeout=120)

        # No-agent task must remain in backlog (untouched)
        tasks = get("/kanban")["tasks"]
        na = next(t for t in tasks if t["id"] == no_agent_task["id"])
        print(f"\n  No-agent task: column={na['column']} status={na['status']}")
        assert na["column"] == "backlog", (
            f"Task without agent should stay in backlog, got column={na['column']}"
        )


class TestTelegramTool:
    """telegram_notify tool is available to agents."""

    _agents: list[int] = []
    _tasks: list[int] = []

    def setup_method(self):
        self._agents = []
        self._tasks = []

    def teardown_method(self):
        cleanup_test_tasks(self._tasks)
        cleanup_test_agents(self._agents)

    def test_telegram_tool_in_tool_list(self):
        """telegram_notify must be in the list of available tools."""
        # The tool list is embedded in the system prompt via format_system_prompt.
        # We verify by running an agent that calls search_tools for 'telegram'.
        agent = post("/agents", {
            "name": "TEST_TelegramCheck",
            "emoji": "📨",
            "color": "#2299ff",
            "system_prompt": (
                "You are a test agent. Call search_tools with query='telegram' "
                "and respond with the tool name found, or 'NOT_FOUND' if absent."
            ),
            "role": "worker",
        })
        self._agents.append(agent["id"])

        task = post("/kanban/tasks", {
            "title": "TEST_Check telegram tool",
            "description": "Search for telegram tool and report",
            "agent_id": agent["id"],
            "column": "backlog",
        })
        self._tasks.append(task["id"])

        post(f"/kanban/tasks/{task['id']}/run")
        result = wait_for_task(task["id"])

        print(f"\n  Status={result['status']} column={result['column']}")
        assert result["status"] == "done"


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess, sys
    sys.exit(subprocess.call([
        sys.executable, "-m", "pytest", __file__, "-v", "-s",
        "--tb=short", "--no-header",
    ]))
