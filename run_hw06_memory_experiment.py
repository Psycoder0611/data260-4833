"""HW6 Part 3: run the fixed 30-message conversation for each memory setting, then the probes.

Needs the FastAPI app running on port 8333, MongoDB and Ollama (qwen3:8b, nomic-embed-text).
Example:  python run_hw06_memory_experiment.py --configs n4,n12,n30,compress
"""
import argparse
import csv
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml

from hw6 import config

CONVERSATION_FILE = config.REPO_ROOT / "data" / "hw6_conversation_30.json"
PROBES_FILE = config.REPO_ROOT / "reports" / "hw06" / "memory_probes.yaml"
RAW_DIR = config.REPO_ROOT / "reports" / "hw06" / "raw"

SETTINGS = {
    "n4": {"label": "SHORT_TERM_N=4", "short_term_n": 4, "memory_policy": "none"},
    "n12": {"label": "SHORT_TERM_N=12", "short_term_n": 12, "memory_policy": "none"},
    "n30": {"label": "SHORT_TERM_N=30", "short_term_n": 30, "memory_policy": "none"},
    "compress": {
        "label": "Compression policy (N=30, last 6 verbatim)",
        "short_term_n": 30,
        "memory_policy": "compress_older",
    },
}

TURN_COLUMNS = [
    "setting", "turn", "timestamp", "user_id", "session_id",
    "prompt_tokens", "completion_tokens",
    "system_primer_tokens", "long_term_tokens", "short_term_tokens",
    "episodic_tokens", "current_message_tokens",
    "aux_prompt_tokens", "aux_completion_tokens",
    "model_latency_ms", "latency_ms",
    "short_term_count", "episodic_facts_used", "session_summary_used", "lifetime_summary_used",
]


def stamp() -> str:
    """Return a readable local timestamp for console output."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def post_chat(base_url: str, payload: dict) -> dict:
    """POST one chat request and return the JSON response (raises on HTTP errors)."""
    response = requests.post(f"{base_url}/api/chat", json=payload, timeout=600)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def score_answer(answer: str, probe: dict) -> dict:
    """Score one probe reply: 1 + round(4 * matched / total)."""
    matched = []
    for fact in probe["facts"]:
        if any(re.search(pattern, answer, re.IGNORECASE) for pattern in fact["patterns"]):
            matched.append(fact["id"])
    total = len(probe["facts"])
    return {"matched": matched, "total": total, "score": 1 + round(4 * len(matched) / total)}


def turn_row(setting: str, turn: int, data: dict) -> dict:
    """Flatten one chat response into a CSV row."""
    usage = data["usage"]
    used = data["memory_used"]
    row = {
        "setting": setting,
        "turn": turn,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user_id": data["user_id"],
        "session_id": data["session_id"],
        "short_term_count": used["short_term_count"],
        "episodic_facts_used": len(used["episodic_facts"]),
        "session_summary_used": bool(used["session_summary"]),
        "lifetime_summary_used": bool(used["lifetime_summary"]),
    }
    for column in TURN_COLUMNS:
        if column in usage:
            row[column] = usage[column]
    return row


def run_setting(key: str, base_url: str, messages: list, probes: list, run_tag: str) -> dict:
    """Run the 30 messages and the probes for one setting; write raw files; return a summary."""
    setting = SETTINGS[key]
    user_id = f"exp_{key}_{run_tag}"
    session_id = f"session_{key}"
    knobs = {"short_term_n": setting["short_term_n"], "memory_policy": setting["memory_policy"]}
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[{stamp()}] === {setting['label']} | user {user_id} ===", flush=True)

    rows, transcript = [], []
    for turn, text in enumerate(messages, start=1):
        data = post_chat(base_url, {"user_id": user_id, "session_id": session_id, "message": text, **knobs})
        rows.append(turn_row(key, turn, data))
        transcript.append({"turn": turn, "user": text, "assistant": data["reply"]})
        usage = data["usage"]
        print(
            f"[{stamp()}] turn {turn:2d}/{len(messages)} prompt={usage['prompt_tokens']:5d} "
            f"completion={usage['completion_tokens']:4d} latency={usage['latency_ms']:8.1f} ms",
            flush=True,
        )

    with (RAW_DIR / f"turns_{key}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TURN_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with (RAW_DIR / f"transcript_{key}.jsonl").open("w", encoding="utf-8") as handle:
        for item in transcript:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[{stamp()}] --- probes for {setting['label']} ---", flush=True)
    results = []
    for probe in probes:
        data = post_chat(
            base_url,
            {"user_id": user_id, "session_id": session_id, "message": probe["question"], "persist": False, **knobs},
        )
        scored = score_answer(data["reply"], probe)
        results.append(
            {
                "probe": probe["id"],
                "question": probe["question"],
                "answer": data["reply"],
                "matched": scored["matched"],
                "score": scored["score"],
                "prompt_tokens": data["usage"]["prompt_tokens"],
            }
        )
        print(f"[{stamp()}] {probe['id']} score={scored['score']} matched={scored['matched']}", flush=True)
    (RAW_DIR / f"probes_{key}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    def column(name: str) -> list:
        return [float(row[name]) for row in rows]

    summary = {
        "label": setting["label"],
        "short_term_n": setting["short_term_n"],
        "memory_policy": setting["memory_policy"],
        "user_id": user_id,
        "turns": len(rows),
        "mean_prompt_tokens": round(statistics.mean(column("prompt_tokens")), 1),
        "mean_completion_tokens": round(statistics.mean(column("completion_tokens")), 1),
        "mean_latency_ms": round(statistics.mean(column("latency_ms")), 1),
        "mean_model_latency_ms": round(statistics.mean(column("model_latency_ms")), 1),
        "total_prompt_tokens": int(sum(column("prompt_tokens"))),
        "total_completion_tokens": int(sum(column("completion_tokens"))),
        "total_aux_prompt_tokens": int(sum(column("aux_prompt_tokens"))),
        "total_aux_completion_tokens": int(sum(column("aux_completion_tokens"))),
        "mean_probe_score": round(statistics.mean(item["score"] for item in results), 2),
        "probe_scores": {item["probe"]: item["score"] for item in results},
    }
    print(
        f"[{stamp()}] SUMMARY {setting['label']}: prompt/turn={summary['mean_prompt_tokens']} "
        f"latency={summary['mean_latency_ms']} ms probe={summary['mean_probe_score']}",
        flush=True,
    )
    return summary


def main() -> int:
    """Run the chosen settings and merge their summaries into raw/summary.json."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=f"http://127.0.0.1:{config.PORT_BASE}")
    parser.add_argument("--configs", default="n4,n12,n30,compress", help="comma list from: n4,n12,n30,compress")
    args = parser.parse_args()

    messages = json.loads(CONVERSATION_FILE.read_text(encoding="utf-8"))
    probes = yaml.safe_load(PROBES_FILE.read_text(encoding="utf-8"))["probes"]
    if len(messages) != 30 or len(probes) != 5:
        print("Expected 30 messages and 5 probes.")
        return 1
    keys = [item.strip() for item in args.configs.split(",") if item.strip()]
    unknown = [key for key in keys if key not in SETTINGS]
    if unknown:
        print(f"Unknown settings: {unknown}")
        return 1

    run_tag = datetime.now().strftime("%Y%m%d%H%M%S")
    summary_path = RAW_DIR / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    started = time.time()
    for key in keys:
        summary[key] = run_setting(key, args.base_url, messages, probes, run_tag)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{stamp()}] done in {round((time.time() - started) / 60, 1)} minutes -> {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
