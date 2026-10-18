"""HW6 smoke test. Writes reports/hw06/verification.json.

Starts the FastAPI app on PORT_BASE if it is not already running, checks the basics
(MongoDB, CRUD, chat memory, files), then stops anything it started. It does not change
application code; it only creates and removes its own test records.

Run:  python verify_hw06.py
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

HOMEWORK = 6
SID4 = 4833
PORT_BASE = 8333
PREFIX = "s4833"
SEED = 4833
VERIFY_SEED = 264833
MODEL = "qwen3:8b"
EMBEDDING_MODEL = "nomic-embed-text"
BASE = f"http://127.0.0.1:{PORT_BASE}"
OUTPUT_PATH = ROOT / "reports" / "hw06" / "verification.json"
TEST_USER = f"verify_{VERIFY_SEED}"
TEST_TITLE = f"verify-hw06-{VERIFY_SEED}"


def git_output(*args):
    """Return the output of a git command, or an empty string if git fails."""
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=ROOT)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def add_check(checks, name, passed, details):
    """Record one check result."""
    checks.append({"name": name, "passed": bool(passed), "details": str(details)})


def run_check(checks, name, function):
    """Run function() -> (passed, details); a crash becomes a failed check."""
    try:
        passed, details = function()
    except Exception as exc:  # a failed check must not stop the others
        passed, details = False, f"{type(exc).__name__}: {exc}"
    add_check(checks, name, passed, details)
    return passed


def server_is_up():
    """Return True when /docs answers on PORT_BASE."""
    try:
        return requests.get(f"{BASE}/docs", timeout=3).status_code == 200
    except requests.RequestException:
        return False


def start_server_if_needed():
    """Start uvicorn if nothing answers on PORT_BASE; return the process or None."""
    if server_is_up():
        return None
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if server_is_up():
            break
        time.sleep(1)
    return process


def cleanup_test_data():
    """Remove the records this script created (messages, summaries, episodes, trials)."""
    from hw6 import config
    from hw6.mongo import get_collection

    for name in (config.MESSAGES_COLLECTION, config.SUMMARIES_COLLECTION, config.EPISODES_COLLECTION):
        get_collection(name).delete_many({"user_id": TEST_USER})
    get_collection(config.TRIALS_COLLECTION).delete_many({"trialTitle": TEST_TITLE})


def main():
    """Run all checks and write verification.json."""
    checks = []
    process = start_server_if_needed()
    state = {}

    def check_server():
        response = requests.get(f"{BASE}/docs", timeout=5)
        return response.status_code == 200, f"GET /docs returned HTTP {response.status_code}"

    def check_earlier_routes():
        paths = requests.get(f"{BASE}/openapi.json", timeout=5).json()["paths"]
        needed = ["/api/trials", "/api/hw4/trials", "/api/hw5/trials", "/api/hw5/organizations", "/api/hw6/trials", "/api/chat"]
        missing = [path for path in needed if path not in paths]
        return not missing, "HW2-HW6 routes all registered" if not missing else f"missing: {missing}"

    def check_mongo():
        from hw6 import config
        from hw6.mongo import get_db, ping

        ping()
        names = set(get_db().list_collection_names())
        needed = {"clinical_trials", "messages", "summaries", "episodes"}
        missing = needed - names
        return (config.MONGODB_DB == f"{PREFIX}_doc") and not missing, (
            f"database {config.MONGODB_DB}; collections present: {sorted(names & needed)}; missing: {sorted(missing)}"
        )

    def check_create():
        body = {"trialTitle": TEST_TITLE, "description": "smoke test", "phase": "phase2", "scheduledDate": "2026-10-15T10:00:00"}
        response = requests.post(f"{BASE}/api/hw6/trials", json=body, timeout=10)
        if response.status_code == 201:
            state["trial_id"] = response.json()["id"]
        return response.status_code == 201 and response.json().get("status") == "recruiting", (
            f"POST returned HTTP {response.status_code}; default status = {response.json().get('status')}"
        )

    def check_list():
        rows = requests.get(f"{BASE}/api/hw6/trials", timeout=10).json()
        return any(row["id"] == state.get("trial_id") for row in rows), f"GET list returned {len(rows)} trials"

    def check_get_update():
        trial_id = state["trial_id"]
        one = requests.get(f"{BASE}/api/hw6/trials/{trial_id}", timeout=10)
        updated = requests.put(f"{BASE}/api/hw6/trials/{trial_id}", json={"status": "active"}, timeout=10)
        return one.status_code == 200 and updated.status_code == 200 and updated.json()["status"] == "active", (
            f"GET by id HTTP {one.status_code}; PUT HTTP {updated.status_code}"
        )

    def check_errors():
        bad_enum = requests.post(f"{BASE}/api/hw6/trials", json={"trialTitle": "x", "phase": "phase9", "scheduledDate": "2026-10-15T10:00:00"}, timeout=10)
        missing = requests.post(f"{BASE}/api/hw6/trials", json={"phase": "phase2", "scheduledDate": "2026-10-15T10:00:00"}, timeout=10)
        bad_id = requests.get(f"{BASE}/api/hw6/trials/not-an-id", timeout=10)
        unknown = requests.get(f"{BASE}/api/hw6/trials/64b64b64b64b64b64b64b64b", timeout=10)
        codes = (bad_enum.status_code, missing.status_code, bad_id.status_code, unknown.status_code)
        return codes == (422, 422, 400, 404), f"invalid enum/missing field/bad id/unknown id -> {codes}"

    def check_delete():
        response = requests.delete(f"{BASE}/api/hw6/trials/{state['trial_id']}", timeout=10)
        again = requests.get(f"{BASE}/api/hw6/trials/{state['trial_id']}", timeout=10)
        return response.status_code == 204 and again.status_code == 404, f"DELETE HTTP {response.status_code}; then GET HTTP {again.status_code}"

    def check_chat():
        body = {"user_id": TEST_USER, "session_id": "verify", "message": "Hi, I'm Sam and my favourite colour is green."}
        response = requests.post(f"{BASE}/api/chat", json=body, timeout=600)
        data = response.json() if response.status_code == 200 else {}
        ok = response.status_code == 200 and bool(data.get("reply")) and "memory_used" in data and data["usage"]["prompt_tokens"] > 0
        return ok, f"HTTP {response.status_code}; reply length {len(data.get('reply', ''))}; usage keys {sorted(data.get('usage', {}))[:4]}"

    def check_memory_endpoint():
        data = requests.get(f"{BASE}/api/memory/{TEST_USER}", timeout=10).json()
        return len(data.get("messages", [])) >= 2, f"{len(data.get('messages', []))} messages returned"

    def check_aggregate_endpoint():
        data = requests.get(f"{BASE}/api/aggregate/{TEST_USER}", timeout=10).json()
        return bool(data.get("daily_message_counts")), f"daily counts: {data.get('daily_message_counts')}"

    def check_probes_file():
        probes = yaml.safe_load((ROOT / "reports/hw06/memory_probes.yaml").read_text(encoding="utf-8"))["probes"]
        ok = len(probes) == 5 and all(p.get("question") and p.get("expected_answer") and p.get("facts") for p in probes)
        return ok, f"{len(probes)} probes with question, expected answer and facts"

    def check_raw_files():
        raw = ROOT / "reports/hw06/raw"
        problems = []
        for key in ("n4", "n12", "n30", "compress"):
            csv_path, probe_path = raw / f"turns_{key}.csv", raw / f"probes_{key}.json"
            if not csv_path.exists() or len(csv_path.read_text(encoding="utf-8").strip().splitlines()) != 31:
                problems.append(f"turns_{key}.csv (need header + 30 rows)")
            if not probe_path.exists() or len(json.loads(probe_path.read_text(encoding="utf-8"))) != 5:
                problems.append(f"probes_{key}.json (need 5 results)")
        if not (raw / "summary.json").exists():
            problems.append("summary.json")
        return not problems, "all raw experiment files found" if not problems else f"problems: {problems}"

    def check_agent_and_memory_files():
        agent = (ROOT / "AGENT.md").read_text(encoding="utf-8")
        memory_path = ROOT / "MEMORY.md"
        bullets = len(re.findall(r"^- ", agent.split("# Project instructions")[-1], flags=re.MULTILINE))
        return memory_path.exists() and bullets >= 5, f"AGENT.md has {bullets} bullets in the HW6 section; MEMORY.md exists: {memory_path.exists()}"

    def check_commands():
        outputs = {}
        for command in ("/help", "/memory"):
            result = subprocess.run([sys.executable, "file_memory_chat.py", "--once", command], capture_output=True, text=True, cwd=ROOT, timeout=60)
            outputs[command] = result.stdout
        ok = "/compact" in outputs["/help"] and "MEMORY.md" in outputs["/memory"]
        return ok, "/help and /memory run and print expected text"

    def check_compliance():
        result = subprocess.run([sys.executable, "check_agentmd_compliance.py"], capture_output=True, text=True, cwd=ROOT, timeout=60)
        return result.returncode == 0, "AGENT.md compliance checker passed" if result.returncode == 0 else result.stdout[-300:]

    def check_offline_tests():
        result = subprocess.run([sys.executable, "-m", "pytest", "test_hw6_offline.py", "-q"], capture_output=True, text=True, cwd=ROOT, timeout=300)
        match = re.search(r"(\d+) passed", result.stdout)
        return result.returncode == 0, match.group(0) if match else result.stdout[-300:]

    def check_report_files():
        names = ["RUN_LOG.txt", "METRICS.md", "AI_USE.md", "memory_probes.yaml"]  # report.pdf is exported from the Word file after this run
        missing = [name for name in names if not (ROOT / "reports/hw06" / name).exists() or (ROOT / "reports/hw06" / name).stat().st_size == 0]
        return not missing, "RUN_LOG, METRICS, AI_USE and memory_probes present (report.pdf is added after this run)" if not missing else f"missing or empty: {missing}"

    try:
        run_check(checks, "FastAPI backend responds on PORT_BASE", check_server)
        run_check(checks, "HW2-HW6 routes are all registered (nothing removed)", check_earlier_routes)
        run_check(checks, "MongoDB connection works, s4833_doc has the four collections", check_mongo)
        if run_check(checks, "POST /api/hw6/trials creates a trial (default status recruiting)", check_create):
            run_check(checks, "GET /api/hw6/trials lists it", check_list)
            run_check(checks, "GET by id and PUT update work", check_get_update)
            run_check(checks, "DELETE removes it", check_delete)
        run_check(checks, "Validation and error codes (422, 422, 400, 404)", check_errors)
        if run_check(checks, "POST /api/chat returns an assistant reply and memory metadata", check_chat):
            run_check(checks, "GET /api/memory/{user_id} returns the messages", check_memory_endpoint)
            run_check(checks, "GET /api/aggregate/{user_id} returns daily counts", check_aggregate_endpoint)
        run_check(checks, "memory_probes.yaml has 5 probes", check_probes_file)
        run_check(checks, "Raw experiment files exist (30 rows and 5 probes per setting)", check_raw_files)
        run_check(checks, "AGENT.md and MEMORY.md exist", check_agent_and_memory_files)
        run_check(checks, "/help and /memory commands run", check_commands)
        run_check(checks, "AGENT.md compliance check passes", check_compliance)
        run_check(checks, "Offline tests pass", check_offline_tests)
        run_check(checks, "Required report files exist (report.pdf is added after this run)", check_report_files)
    finally:
        try:
            cleanup_test_data()
        except Exception as exc:
            add_check(checks, "Cleanup of verification test data", False, str(exc))
        if process is not None:
            process.terminate()

    result = {
        "homework": HOMEWORK,
        "sid4": SID4,
        "port_base": PORT_BASE,
        "prefix": PREFIX,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "model": MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "commit_hash": git_output("rev-parse", "HEAD"),
        "uncommitted_changes": bool(git_output("status", "--porcelain")),
        "overall_pass": all(check["passed"] for check in checks),
        "checks": checks,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for check in checks:
        print(f"[{'PASS' if check['passed'] else 'FAIL'}] {check['name']} - {check['details']}")
    print(f"\nOverall: {'PASS' if result['overall_pass'] else 'FAIL'}  ->  {OUTPUT_PATH}")
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
