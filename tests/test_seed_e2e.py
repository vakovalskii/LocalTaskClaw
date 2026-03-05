"""
End-to-end tests for the seeded kanban pipeline.

Tests that seed_kanban.py created the right agents/tasks,
then runs the orchestrator and verifies the full cycle completes:
  backlog → in_progress → review → done

Run:
    cd /Users/v.kovalskii/LocalTaskClaw
    python scripts/seed_kanban.py --reset   # seed fresh data first
    ./venv/bin/pytest tests/test_seed_e2e.py -v -s
"""

import os
import sys
import time
import httpx
import pytest
import subprocess

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("API_URL", "http://localhost:11387")
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
PYTHON = sys.executable

# How long to wait for a single agent task to finish
WORKER_TIMEOUT = 240   # seconds — workers do web searches, need time
ORC_TIMEOUT = 120      # seconds — orchestrator just dispatches
POLL_INTERVAL = 4

EXPECTED_WORKER_NAMES = {
    "News Analyst",
    "Web Researcher",
    "Code Reviewer",
    "Writer",
}
ORCHESTRATOR_NAME = "Chief Orchestrator"
ORCHESTRATOR_TASK_TITLE = "Orchestration Cycle"
ORCHESTRATOR_REPEAT_MINUTES = 5

EXPECTED_TASK_TITLES = {
    "AI News Digest",
    "Top Open-Source LLMs for Local Deployment",
    "Workspace Structure Review",
    "Essay: AI Agents in 2027",
    "Comparison: Claude vs GPT-4 vs Gemini",
}


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
HEADERS = (
    {"X-Api-Key": API_SECRET, "Content-Type": "application/json"}
    if API_SECRET
    else {"Content-Type": "application/json"}
)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def get(path: str) -> dict:
    r = httpx.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def post(path: str, data: dict = None) -> dict:
    r = httpx.post(f"{BASE_URL}{path}", json=data or {}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def delete(path: str):
    r = httpx.delete(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()


def wait_for_task(task_id: int, timeout: int = WORKER_TIMEOUT, label: str = "") -> dict:
    """Poll until task leaves 'running' status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        tasks = get("/kanban")["tasks"]
        task = next((t for t in tasks if t["id"] == task_id), None)
        assert task is not None, f"Task #{task_id} disappeared from board"
        if task["status"] != "running":
            return task
        elapsed = int(time.time() - (deadline - timeout))
        print(f"  ⏳ [{label or task_id}] running... {elapsed}s elapsed")
        time.sleep(POLL_INTERVAL)
    pytest.fail(f"Task #{task_id} still running after {timeout}s")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def seed_board():
    """Run seed script once before all tests in this module."""
    print("\n🌱 Running seed_kanban.py --reset ...")
    result = subprocess.run(
        [PYTHON, os.path.join(SCRIPTS_DIR, "seed_kanban.py"), "--reset"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        pytest.fail(f"seed_kanban.py failed with code {result.returncode}")
    print(result.stdout)
    yield


# ── Tests: structure ─────────────────────────────────────────────────────────

class TestSeedStructure:
    """Verify seed_kanban.py created the right agents and tasks."""

    def test_api_is_up(self):
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        assert r.status_code == 200

    def test_worker_agents_created(self):
        agents = get("/agents")["agents"]
        names = {a["name"] for a in agents}
        missing = EXPECTED_WORKER_NAMES - names
        assert not missing, f"Missing worker agents: {missing}"

    def test_orchestrator_agent_created(self):
        agents = get("/agents")["agents"]
        orc = next((a for a in agents if a["name"] == ORCHESTRATOR_NAME), None)
        assert orc is not None, f"Orchestrator '{ORCHESTRATOR_NAME}' not found"
        assert orc["role"] == "orchestrator", f"Expected role=orchestrator, got {orc['role']}"

    def test_worker_agents_have_correct_roles(self):
        agents = get("/agents")["agents"]
        for a in agents:
            if a["name"] in EXPECTED_WORKER_NAMES:
                assert a["role"] == "worker", f"{a['name']} should have role=worker, got {a['role']}"

    def test_worker_tasks_in_backlog(self):
        tasks = get("/kanban")["tasks"]
        titles = {t["title"] for t in tasks}
        missing = EXPECTED_TASK_TITLES - titles
        assert not missing, f"Missing tasks: {missing}"

        for t in tasks:
            if t["title"] in EXPECTED_TASK_TITLES:
                assert t["column"] == "backlog", (
                    f"Task '{t['title']}' should be in backlog, got {t['column']}"
                )
                assert t["agent_id"] is not None, (
                    f"Task '{t['title']}' has no agent assigned"
                )

    def test_orchestrator_task_exists_with_repeat(self):
        tasks = get("/kanban")["tasks"]
        orc_task = next((t for t in tasks if t["title"] == ORCHESTRATOR_TASK_TITLE), None)
        assert orc_task is not None, f"Orchestrator task '{ORCHESTRATOR_TASK_TITLE}' not found"
        assert orc_task["repeat_minutes"] == ORCHESTRATOR_REPEAT_MINUTES, (
            f"Expected repeat_minutes={ORCHESTRATOR_REPEAT_MINUTES}, got {orc_task['repeat_minutes']}"
        )
        assert orc_task["column"] == "backlog"

    def test_each_task_agent_assignment(self):
        """Every worker task must be assigned to a valid agent with matching role."""
        tasks = get("/kanban")["tasks"]
        agents = {a["id"]: a for a in get("/agents")["agents"]}

        for t in tasks:
            if t["title"] not in EXPECTED_TASK_TITLES:
                continue
            assert t["agent_id"] is not None, f"Task '{t['title']}' has no agent"
            agent = agents.get(t["agent_id"])
            assert agent is not None, f"Task '{t['title']}' references missing agent #{t['agent_id']}"
            assert agent["role"] == "worker", (
                f"Task '{t['title']}' should be assigned to a worker, got role={agent['role']}"
            )

    def test_orchestrator_task_assigned_to_orchestrator(self):
        tasks = get("/kanban")["tasks"]
        agents = {a["id"]: a for a in get("/agents")["agents"]}
        orc_task = next((t for t in tasks if t["title"] == ORCHESTRATOR_TASK_TITLE), None)
        assert orc_task is not None
        agent = agents.get(orc_task["agent_id"])
        assert agent is not None
        assert agent["role"] == "orchestrator"


# ── Tests: single worker ──────────────────────────────────────────────────────

class TestWorkerExecution:
    """Run one worker task end-to-end, verify artifact is produced."""

    def test_reviewer_completes_workspace_review(self):
        """
        'Code Reviewer' runs workspace review — requires no external API,
        just list_files + write_file. Fast and reliable.
        """
        tasks = get("/kanban")["tasks"]
        task = next((t for t in tasks if t["title"] == "Workspace Structure Review"), None)
        assert task is not None, "Workspace review task not found"

        # Reset to backlog if it drifted
        if task["column"] != "backlog":
            post(f"/kanban/tasks/{task['id']}/move", {"column": "backlog"})
            time.sleep(1)

        print(f"\n  Running task #{task['id']}: {task['title']}")
        run_resp = post(f"/kanban/tasks/{task['id']}/run")
        assert run_resp["status"] == "started"

        # Verify it moved to in_progress
        time.sleep(1)
        live = next(t for t in get("/kanban")["tasks"] if t["id"] == task["id"])
        assert live["status"] == "running", f"Expected running, got {live['status']}"
        assert live["column"] == "in_progress"

        # Wait for completion
        result = wait_for_task(task["id"], timeout=WORKER_TIMEOUT, label="workspace-review")
        print(f"  ✓ Final: status={result['status']} column={result['column']}")

        assert result["status"] == "done", f"Expected done, got {result['status']}"
        assert result["column"] == "review", f"Expected review, got {result['column']}"
        assert result["artifact"] is not None, "Expected artifact path to be set"

    def test_writer_produces_artifact(self):
        """
        'Writer' writes an essay — no external search needed, pure generation.
        """
        tasks = get("/kanban")["tasks"]
        task = next((t for t in tasks if t["title"] == "Essay: AI Agents in 2027"), None)
        assert task is not None, "Essay task not found"

        if task["column"] != "backlog":
            post(f"/kanban/tasks/{task['id']}/move", {"column": "backlog"})
            time.sleep(1)

        print(f"\n  Running task #{task['id']}: {task['title']}")
        post(f"/kanban/tasks/{task['id']}/run")

        result = wait_for_task(task["id"], timeout=WORKER_TIMEOUT, label="essay")
        print(f"  ✓ Final: status={result['status']} artifact={result.get('artifact')}")

        assert result["status"] == "done"
        assert result["column"] == "review"
        assert result["artifact"] is not None

        # Check artifact file has at least a completion message.
        # The agent may write the actual content to a separate file via write_file
        # and return a short confirmation as result.text — both are valid.
        artifact_path = result["artifact"]
        if artifact_path and os.path.exists(artifact_path):
            content = open(artifact_path, errors="replace").read()
            assert len(content) > 20, f"Artifact suspiciously empty ({len(content)} chars)"
            print(f"  ✓ Artifact: {len(content)} chars at {artifact_path}")


# ── Tests: orchestrator ───────────────────────────────────────────────────────

class TestOrchestratorCycle:
    """
    Full orchestration cycle:
    - Reset all worker tasks to backlog
    - Run orchestrator
    - Verify orchestrator dispatched workers (they moved to in_progress)
    - Wait for workers, verify artifacts produced
    """

    @pytest.fixture(autouse=True)
    def reset_tasks_to_backlog(self):
        """Before each test, move all worker tasks back to backlog/idle."""
        tasks = get("/kanban")["tasks"]
        for t in tasks:
            if t["title"] in EXPECTED_TASK_TITLES and t["column"] != "backlog":
                try:
                    post(f"/kanban/tasks/{t['id']}/move", {"column": "backlog"})
                except Exception:
                    pass
        # Wait for any running tasks to stop
        time.sleep(2)
        yield
        # Cleanup: cancel anything still running after the test
        tasks = get("/kanban")["tasks"]
        for t in tasks:
            if t["status"] == "running":
                try:
                    post(f"/kanban/tasks/{t['id']}/cancel")
                except Exception:
                    pass

    def test_orchestrator_dispatches_all_backlog_tasks(self):
        """
        Orchestrator must call kanban_run for each backlog task with an agent.
        After orchestrator finishes, all worker tasks should be running or past backlog.
        """
        tasks = get("/kanban")["tasks"]
        orc_task = next((t for t in tasks if t["title"] == ORCHESTRATOR_TASK_TITLE), None)
        assert orc_task is not None

        backlog_worker_ids = [
            t["id"] for t in tasks
            if t["title"] in EXPECTED_TASK_TITLES and t["column"] == "backlog"
        ]
        assert len(backlog_worker_ids) > 0, "No backlog worker tasks to dispatch"
        print(f"\n  Backlog tasks to dispatch: {backlog_worker_ids}")

        # Move orchestrator to backlog if needed
        if orc_task["column"] != "backlog":
            post(f"/kanban/tasks/{orc_task['id']}/move", {"column": "backlog"})
            time.sleep(1)

        # Run orchestrator
        post(f"/kanban/tasks/{orc_task['id']}/run")
        print(f"  Orchestrator #{orc_task['id']} started")

        # Wait for orchestrator to finish dispatching
        orc_result = wait_for_task(orc_task["id"], timeout=ORC_TIMEOUT, label="orchestrator")
        print(f"  Orchestrator done: status={orc_result['status']} column={orc_result['column']}")
        # Orchestrator with repeat_minutes > 0 returns to backlog after each cycle (by design)
        assert orc_result["column"] in ("review", "done", "backlog"), (
            f"Orchestrator ended in unexpected column: {orc_result['column']}"
        )
        assert orc_result["status"] != "error", "Orchestrator errored out"

        # Most worker tasks should have left backlog (dispatched by orchestrator).
        # Allow at most 1 undispatched task: the orchestrator may skip the second
        # task assigned to the same agent that is already running.
        current = get("/kanban")["tasks"]
        not_dispatched = []
        for tid in backlog_worker_ids:
            t = next(t for t in current if t["id"] == tid)
            print(f"  Task #{tid} '{t['title']}': column={t['column']} status={t['status']}")
            dispatched = (
                t["column"] != "backlog"
                or t["status"] in ("running", "done", "verified")
            )
            if not dispatched:
                not_dispatched.append(f"#{tid} '{t['title']}' (column={t['column']} status={t['status']})")
        assert len(not_dispatched) <= 1, (
            f"Orchestrator failed to dispatch {len(not_dispatched)} tasks:\n"
            + "\n".join(not_dispatched)
        )

    def test_orchestrator_verifies_completed_workers(self):
        """
        Run one worker first → puts it in review.
        Then run orchestrator → it should verify the review task (approve/reject).
        Task should end up in done or backlog (retry), NOT stay in review.
        """
        tasks = get("/kanban")["tasks"]

        # Pick one worker task (workspace review — no external deps)
        worker_task = next(
            (t for t in tasks if t["title"] == "Workspace Structure Review"), None
        )
        assert worker_task is not None

        orc_task = next((t for t in tasks if t["title"] == ORCHESTRATOR_TASK_TITLE), None)
        assert orc_task is not None

        # Run the worker directly to get it to review
        print(f"\n  Running worker #{worker_task['id']} first...")
        post(f"/kanban/tasks/{worker_task['id']}/run")
        worker_result = wait_for_task(
            worker_task["id"], timeout=WORKER_TIMEOUT, label="worker-pre-verify"
        )
        print(f"  Worker done: column={worker_result['column']} artifact={bool(worker_result.get('artifact'))}")

        if worker_result["column"] != "review":
            pytest.skip(f"Worker ended in {worker_result['column']}, skipping verify test")

        # Move all OTHER worker tasks to done so orchestrator focuses only on review
        for t in get("/kanban")["tasks"]:
            if t["title"] in EXPECTED_TASK_TITLES and t["id"] != worker_task["id"]:
                if t["column"] == "backlog":
                    post(f"/kanban/tasks/{t['id']}/move", {"column": "done"})

        # Move orchestrator back to backlog
        if orc_task["column"] != "backlog":
            post(f"/kanban/tasks/{orc_task['id']}/move", {"column": "backlog"})
        time.sleep(1)

        # Run orchestrator — should verify the review task
        print(f"  Running orchestrator #{orc_task['id']} to verify...")
        post(f"/kanban/tasks/{orc_task['id']}/run")
        wait_for_task(orc_task["id"], timeout=ORC_TIMEOUT, label="orchestrator-verify")

        # After orchestrator verify:
        # - approved=true  → stays in review, status="verified" (human moves to done)
        # - approved=false → back to backlog for retry
        current = get("/kanban")["tasks"]
        wt = next(t for t in current if t["id"] == worker_task["id"])
        print(f"  After verify: column={wt['column']} status={wt['status']}")
        assert wt["status"] in ("verified", "idle"), (
            f"Orchestrator should have verified the task: expected status=verified or idle(retry), "
            f"got column={wt['column']} status={wt['status']}"
        )


# ── Tests: repeat/heartbeat ──────────────────────────────────────────────────

class TestOrchestratorRepeat:
    """Orchestrator task has repeat_minutes set and auto-triggers."""

    def test_orchestrator_task_has_repeat_minutes(self):
        tasks = get("/kanban")["tasks"]
        orc_task = next((t for t in tasks if t["title"] == ORCHESTRATOR_TASK_TITLE), None)
        assert orc_task is not None
        assert orc_task["repeat_minutes"] == ORCHESTRATOR_REPEAT_MINUTES, (
            f"Expected repeat_minutes={ORCHESTRATOR_REPEAT_MINUTES}, "
            f"got {orc_task['repeat_minutes']}"
        )

    def test_run_endpoint_starts_orchestrator(self):
        """POST /run on orchestrator should start it (status=started)."""
        tasks = get("/kanban")["tasks"]
        orc_task = next((t for t in tasks if t["title"] == ORCHESTRATOR_TASK_TITLE), None)
        assert orc_task is not None

        # Reset to backlog if running
        if orc_task["status"] == "running":
            post(f"/kanban/tasks/{orc_task['id']}/cancel")
            time.sleep(2)
            post(f"/kanban/tasks/{orc_task['id']}/move", {"column": "backlog"})

        resp = post(f"/kanban/tasks/{orc_task['id']}/run")
        assert resp["status"] == "started"

        # Give it a moment, then cancel so we don't wait 5 minutes
        time.sleep(2)
        post(f"/kanban/tasks/{orc_task['id']}/cancel")
        time.sleep(1)

        current = next(t for t in get("/kanban")["tasks"] if t["id"] == orc_task["id"])
        assert current["status"] != "running", "Orchestrator should have been cancelled"


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([
        sys.executable, "-m", "pytest", __file__,
        "-v", "-s", "--tb=short", "--no-header",
    ]))
