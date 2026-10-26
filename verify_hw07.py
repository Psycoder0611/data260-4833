"""HW7 smoke test. Writes reports/hw07/verification.json.

Starts the FastAPI app on PORT_BASE if it is not already running, then checks the
basics of every part (JWT login and roles, the agent loop with VERIFY_SEED, the bike
tools, the injection defenses, the file tools and safety gate). It does not change
application code; it only creates and removes its own test trials.

Run:  python verify_hw07.py     (needs MySQL, and Ollama for the agent check)
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from hw7 import config  # noqa: E402

HOMEWORK = 7
BASE = f"http://127.0.0.1:{config.PORT_BASE}"
RAW = ROOT / "reports" / "hw07" / "raw"
OUTPUT_PATH = ROOT / "reports" / "hw07" / "verification.json"
USERS = {name: (password, role) for name, password, role in config.DEMO_USERS}
OFFLINE_TESTS = [
    "test_hw7_offline.py",
    "test_hw7_agent_offline.py",
    "test_hw7_reflexion_offline.py",
    "test_hw7_bike_offline.py",
    "test_hw7_security_offline.py",
    "test_hw7_files_offline.py",
]
RAW_FILES = [
    "reliability_attempts.csv",
    "reliability_summary.json",
    "reliability_injected_summary.json",
    "reflexion_draft_comparison.json",
    "bike_scenario_a_membership_trip_summary.json",
    "bike_scenario_b_payperuse_trip_summary.json",
    "bike_scenario_a_membership_run.json",
    "bike_scenario_b_payperuse_run.json",
    "pricing_snapshot_scenario_a_membership.json",
    "pricing_snapshot_scenario_b_payperuse.json",
    "part5_hostile_results.json",
    "part5_standin_results.json",
    "part6_gate_results.json",
]


def git_output(*args):
    """Return the output of a git command, or an empty string if git fails."""
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, cwd=ROOT
        )
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
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "127.0.0.1", "--port", str(config.PORT_BASE),
        ],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(40):
        if server_is_up():
            break
        time.sleep(1)
    return process


def login(username, password=None):
    """POST /auth/login for a demo user."""
    password = USERS[username][0] if password is None else password
    return requests.post(
        f"{BASE}/auth/login",
        data={"username": username, "password": password},
        timeout=10,
    )


def headers(username):
    """Authorization header for a demo user."""
    return {"Authorization": f"Bearer {login(username).json()['access_token']}"}


def first_org_id():
    """Id of an existing research organization (HW5 data)."""
    from database import db_session_basede26
    from models import ResearchOrganizationDB

    with db_session_basede26() as session:
        org = (
            session.query(ResearchOrganizationDB)
            .order_by(ResearchOrganizationDB.id)
            .first()
        )
    return org.id


def trial_body(org_id):
    """A unique test trial."""
    return {
        "trialTitle": f"verify-hw07-{config.VERIFY_SEED}",
        "trial_code": f"HW7-VERIFY-{int(time.time() * 1000)}",
        "participant_capacity": 10,
        "organization_id": org_id,
    }


def main():
    """Run all checks and write verification.json."""
    checks = []
    created = []
    process = start_server_if_needed()

    def check_server():
        code = requests.get(f"{BASE}/docs", timeout=5).status_code
        return code == 200, f"GET /docs returned HTTP {code}"

    def check_routes():
        paths = list(requests.get(f"{BASE}/openapi.json", timeout=5).json()["paths"])
        exact = ["/auth/login", "/auth/me", "/api/hw7/trials"]
        parts = ["hw4", "hw5", "hw6"]
        missing = [p for p in exact if p not in paths]
        missing += [k for k in parts if not any(k in p for p in paths)]
        return not missing, f"missing: {missing}" if missing else "HW4-HW7 routes found"

    def check_login():
        good = login("writer_user")
        bad = login("writer_user", "wrong-password")
        ok = good.status_code == 200 and bool(good.json().get("access_token"))
        return ok and bad.status_code == 401, (
            f"valid login HTTP {good.status_code} with token, "
            f"wrong password HTTP {bad.status_code}"
        )

    def check_me():
        none = requests.get(f"{BASE}/auth/me", timeout=5)
        bad = requests.get(
            f"{BASE}/auth/me", headers={"Authorization": "Bearer nope"}, timeout=5
        )
        me = requests.get(f"{BASE}/auth/me", headers=headers("reader_user"), timeout=5)
        ok = me.status_code == 200 and me.json().get("role") == "reader"
        return ok and (none.status_code, bad.status_code) == (401, 401), (
            f"no token HTTP {none.status_code}, bad token HTTP {bad.status_code}, "
            f"valid token HTTP {me.status_code} role {me.json().get('role')}"
        )

    def check_roles():
        org = first_org_id()
        url = f"{BASE}/api/hw7/trials"
        reader = requests.post(
            url, json=trial_body(org), headers=headers("reader_user"), timeout=10
        )
        writer = requests.post(
            url, json=trial_body(org), headers=headers("writer_user"), timeout=10
        )
        if writer.status_code == 201:
            created.append(writer.json()["id"])
        trial = f"{url}/{created[0] if created else 0}"
        denied = requests.delete(trial, headers=headers("writer_user"), timeout=10)
        allowed = requests.delete(trial, headers=headers("moderator_user"), timeout=10)
        listing = requests.get(url, headers=headers("reader_user"), timeout=10)
        codes = (
            reader.status_code, writer.status_code, denied.status_code,
            allowed.status_code in (200, 204), listing.status_code,
        )  # fmt: skip
        return codes == (403, 201, 403, True, 200), (
            "reader create / writer create / writer delete / moderator delete ok / "
            f"list -> {codes}"
        )

    def check_hashes():
        from hw7.db import HW7User, SessionLocal

        with SessionLocal() as session:
            rows = {u.username: u.password_hash for u in session.query(HW7User)}
        bad = [
            name for name, (password, _) in USERS.items()
            if name not in rows or rows[name] == password
            or not rows[name].startswith("$2")
        ]  # fmt: skip
        return not bad, f"bcrypt hashes stored for {sorted(rows)}; problems: {bad}"

    def check_agent():
        from hw7 import agent, cases, llm

        case = cases.CASES[0]

        def chat(messages):
            return llm.chat(messages, temperature=0.0, seed=config.VERIFY_SEED)

        result = agent.run_agent(
            case["prompt"], chat_fn=chat, log_path=None, run_id="verify"
        )
        ok = cases.chain_ok(case, result["tool_log"])
        return ok, (
            f"task {case['id']}: {result['tool_calls']} tool calls, stop "
            f"{result['stop_reason']}, seed {config.VERIFY_SEED}"
        )

    def check_bike_tools():
        from hw7 import bike_policy, bike_tools

        csv_path = ROOT / "data" / "bike_scenarios" / "scenario_b_payperuse.csv"
        tools = bike_tools.BikeTools(str(csv_path))
        rows = tools.call("csv_sql", {"sql": "SELECT COUNT(*) AS n FROM trips"})
        write = tools.call("csv_sql", {"sql": "DELETE FROM trips"})
        calc = tools.call("calculator", {"expression": "29*4/8"})
        clean = ROOT / "reports" / "hw07" / "fixtures" / "bike_pricing_clean.txt"
        page = bike_tools.policy_retriever(
            f"file://{clean}", "month pass price", 5, bike_policy.fetch_page
        )
        texts = [p["text"] for p in page["data"]["passages"]]
        ok = (
            rows["success"]
            and rows["data"]["rows"][0]["n"] == 600
            and not write["success"]
            and calc["data"]["value"] == 14.5
            and any("$29" in t for t in texts)
        )
        return ok, "SELECT works, DELETE refused, calculator 14.5, $29 snippet found"

    def check_pinned_snapshot():
        from hw7 import bike_policy

        name = "pricing_snapshot_scenario_a_membership"
        saved = json.loads((RAW / f"{name}.json").read_text())
        now = bike_policy.fetch_page(f"file://{RAW / (name + '.txt')}")["sha256"]
        return now == saved[
            "sha256"
        ], f"snapshot text hash {now[:16]} vs saved {saved['sha256'][:16]}"

    def check_hostile_fixture():
        from hw7 import bike_security

        text = (ROOT / "reports/hw07/fixtures/bike_pricing_hostile.txt").read_text()
        found = [k for k, line in bike_security.INJECTIONS.items() if line in text]
        return len(found) == 3, f"injections present in the fixture: {found}"

    def check_gate():
        from hw7 import file_tools

        ok = (
            file_tools.is_destructive("rm -rf /") is True
            and file_tools.is_destructive("ls -la") is False
            and file_tools.confirm_bash("ls -la")["allow"] is True
            and file_tools.confirm_bash("sudo ls")["allow"] is False
            and file_tools.confirm_bash("sudo ls", auto_approve=True)["allow"] is True
        )
        return ok, "is_destructive and confirm_bash give the expected allow/block"

    def check_offline_tests():
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *OFFLINE_TESTS, "-q"],
            capture_output=True, text=True, cwd=ROOT, timeout=600,
        )  # fmt: skip
        match = re.search(r"(\d+) passed", result.stdout)
        return result.returncode == 0, match.group(0) if match else result.stdout[-300:]

    def check_raw_files():
        missing = [n for n in RAW_FILES if not (RAW / n).exists()]
        return not missing, f"missing raw files: {missing}" if missing else "all found"

    def check_report_files():
        names = ["RUN_LOG.txt", "METRICS.md", "AI_USE.md"]  # PDFs are added after
        folder = ROOT / "reports" / "hw07"
        missing = [n for n in names if not (folder / n).exists()]
        empty = [n for n in names if (folder / n).exists()
                 and (folder / n).stat().st_size == 0]  # fmt: skip
        return not (missing or empty), f"missing: {missing}; empty: {empty}"

    try:
        run_check(checks, "FastAPI backend responds on PORT_BASE", check_server)
        run_check(checks, "HW2-HW7 routes are all registered", check_routes)
        run_check(
            checks, "POST /auth/login: valid -> token, invalid -> 401", check_login
        )
        run_check(
            checks, "GET /auth/me: no or bad token -> 401, valid -> role", check_me
        )
        run_check(
            checks, "Roles: 403 reader create, 201 writer, 403/200 delete", check_roles
        )
        run_check(checks, "Passwords are stored as bcrypt hashes", check_hashes)
        run_check(
            checks,
            "Hand-written agent loop completes a task (VERIFY_SEED)",
            check_agent,
        )
        run_check(
            checks, "Bike tools: read-only SQL, calculator, retriever", check_bike_tools
        )
        run_check(
            checks,
            "Saved pricing snapshot hash matches the fixture",
            check_pinned_snapshot,
        )
        run_check(
            checks, "Hostile fixture holds the three injections", check_hostile_fixture
        )
        run_check(checks, "Safety gate: is_destructive and confirm_bash", check_gate)
        run_check(
            checks, "Offline tests pass (all six HW7 test files)", check_offline_tests
        )
        run_check(checks, "Raw experiment files exist", check_raw_files)
        run_check(
            checks,
            "RUN_LOG, METRICS and AI_USE exist (PDFs added after)",
            check_report_files,
        )
    finally:
        for trial_id in created:  # remove any test trial left behind
            try:
                requests.delete(
                    f"{BASE}/api/hw7/trials/{trial_id}",
                    headers=headers("moderator_user"), timeout=10,
                )  # fmt: skip
            except requests.RequestException:
                pass
        if process is not None:
            process.terminate()

    changes = git_output(
        "status", "--porcelain", "--", ".",
        ":!reports/hw07/verification.json", ":!reports/hw07/*.pdf",
    )  # fmt: skip
    result = {
        "homework": HOMEWORK,
        "sid4": config.SID4,
        "port_base": config.PORT_BASE,
        "prefix": config.PREFIX,
        "seed": config.SEED,
        "verify_seed": config.VERIFY_SEED,
        "model": config.MODEL_NAME,
        "commit_hash": git_output("rev-parse", "HEAD"),
        "uncommitted_changes": bool(changes),
        "overall_pass": all(check["passed"] for check in checks),
        "checks": checks,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for check in checks:
        print(
            f"[{'PASS' if check['passed'] else 'FAIL'}] "
            f"{check['name']} - {check['details']}"
        )
    print(
        f"\nOVERALL: {'PASS' if result['overall_pass'] else 'FAIL'}  ->  {OUTPUT_PATH}"
    )
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
