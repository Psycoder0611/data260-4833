"""Run the HW6 demo calls (for screenshots). Usage: python demo_hw06.py part1 | part2

Needs the FastAPI app running on port 8333 (python main.py) and MongoDB. Part 2 also needs Ollama.
"""
import json
import sys
from datetime import datetime

import requests

BASE = "http://127.0.0.1:8333"
BANNER = "Student: Trapti Kulshrestha | SID4 4833 | HW6 demo"


def show(title, response):
    """Print one request result with its HTTP status."""
    print(f"\n--- {title} -> HTTP {response.status_code}")
    if response.text:
        try:
            print(json.dumps(response.json(), indent=2))
        except ValueError:
            print(response.text)
    return response


def part1():
    """Part 1: CRUD calls and validation tests."""
    trial = {
        "trialTitle": "Glucose Monitoring Study",
        "description": "Study evaluating glucose tracking in adults.",
        "status": "recruiting",
        "phase": "phase2",
        "scheduledDate": "2026-10-15T10:00:00",
    }
    created = show("POST /api/hw6/trials (create)", requests.post(f"{BASE}/api/hw6/trials", json=trial))
    trial_id = created.json()["id"]
    show("POST second trial", requests.post(f"{BASE}/api/hw6/trials", json={**trial, "trialTitle": "Hypertension Drug Trial", "phase": "phase3", "status": "active"}))
    show("GET /api/hw6/trials (all)", requests.get(f"{BASE}/api/hw6/trials"))
    show(f"GET /api/hw6/trials/{trial_id}", requests.get(f"{BASE}/api/hw6/trials/{trial_id}"))
    show("PUT (status -> active, phase -> phase3)", requests.put(f"{BASE}/api/hw6/trials/{trial_id}", json={"status": "active", "phase": "phase3"}))
    missing = {key: value for key, value in trial.items() if key != "trialTitle"}
    show("Validation: missing trialTitle", requests.post(f"{BASE}/api/hw6/trials", json=missing))
    show("Validation: invalid status enum", requests.post(f"{BASE}/api/hw6/trials", json={**trial, "status": "paused"}))
    show("Validation: title longer than 100 characters", requests.post(f"{BASE}/api/hw6/trials", json={**trial, "trialTitle": "x" * 101}))
    show("Validation: wrong date type", requests.post(f"{BASE}/api/hw6/trials", json={**trial, "scheduledDate": "tomorrow"}))
    show("Bad id format", requests.get(f"{BASE}/api/hw6/trials/not-an-id"))
    show("Unknown id", requests.get(f"{BASE}/api/hw6/trials/64b64b64b64b64b64b64b64b"))
    show(f"DELETE /api/hw6/trials/{trial_id}", requests.delete(f"{BASE}/api/hw6/trials/{trial_id}"))
    show("GET deleted trial", requests.get(f"{BASE}/api/hw6/trials/{trial_id}"))
    print("\n(Second trial was kept so MongoDB shows a sample record.)")


MESSAGES = [
    "Hi! I'm Dana, a field ecologist living in Monterey.",
    "I'm planning a 12-day trip to Iceland starting March 3rd.",
    "My cat Biscuit will stay with my neighbour Omar.",
    "What should I pack for cold, wet weather?",
    "I'm vegetarian, so food planning matters too.",
    "My camera is a Nikon Z6 with a 400mm lens.",
    "I'm also writing a paper on seabird nesting, due April 20th.",
    "My co-author is Dr. Lena Okafor.",
    "Any tip for staying focused while writing?",
    "I usually write between 6 and 9 am.",
    "Quick check: what is my cat called and who looks after her?",
]


def part2():
    """Part 2: an 11-message chat in one session, then the memory and aggregate views."""
    user_id = f"demo_{datetime.now().strftime('%H%M%S')}"
    session_id = "session1"
    print(f"user_id={user_id} session_id={session_id}")
    for number, text in enumerate(MESSAGES, start=1):
        data = requests.post(f"{BASE}/api/chat", json={"user_id": user_id, "session_id": session_id, "message": text}, timeout=600).json()
        used = data["memory_used"]
        print(f"\n[{number}] you: {text}")
        print(f"    assistant: {data['reply']}")
        print(
            f"    memory: short-term={used['short_term_count']} | session summary={'yes' if used['session_summary'] else 'no'} | "
            f"lifetime={'yes' if used['lifetime_summary'] else 'no'} | episodic retrieved={len(used['episodic_facts'])}"
        )
        if used["episodic_facts"]:
            print("    retrieved facts:", [item["fact"] for item in used["episodic_facts"]])
        if data["new_memory"]["episodes_added"]:
            print("    stored facts:", [item["fact"] for item in data["new_memory"]["episodes_added"]])
        if data["new_memory"]["session_summary_created"]:
            print("    >> session summary created")
        if data["new_memory"]["lifetime_summary_created"]:
            print("    >> lifetime summary created")
    print("\n--- GET /api/memory/" + user_id)
    print(json.dumps(requests.get(f"{BASE}/api/memory/{user_id}").json(), indent=2)[:6000])
    print("\n--- GET /api/aggregate/" + user_id)
    print(json.dumps(requests.get(f"{BASE}/api/aggregate/{user_id}").json(), indent=2)[:4000])


if __name__ == "__main__":
    print(BANNER)
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if len(sys.argv) < 2 or sys.argv[1] not in ("part1", "part2"):
        print("Usage: python demo_hw06.py part1 | part2")
        sys.exit(1)
    part1() if sys.argv[1] == "part1" else part2()
