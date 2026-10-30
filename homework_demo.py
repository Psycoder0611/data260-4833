"""HW8 Part 1 demo: CREATE then GET over Kafka, with the full message flow logged.

Run (Kafka, worker and API must be up:  docker compose -f docker-compose.hw8.yml up -d):
    python homework_demo.py

Steps (the numbers match the assignment):
 1 create one correlation_id            6 log the response received by the client
 2 send CREATE to s4833_entity_requests  7 extract the generated entity id
 3 log the message sent                  8 send GET with that id
 4 log the worker receiving/processing   9 log the whole GET sequence
 5 log the worker's reply                10 show the entity and confirm the id
The worker's lines (4 and 5) come from the trace file that the worker container
writes to reports/hw08/raw/worker_trace.jsonl; its console shows the same lines.
"""

import argparse
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List

from hw8 import config
from hw8.logs import get_logger, read_jsonl, run_logged
from hw8.rpc_client import KafkaRPC, RpcTimeout

TRIAL = {
    "trialTitle": "Cardiovascular Outcomes Study",
    "sponsor": "Acme Pharma",
    "trial_code": "CT-2026-801",
    "participant_capacity": 240,
    "submitterEmail": "study.office@acme.example",
    "category": "Cardiology",
    "description": "Phase II trial of a new blood pressure treatment.",
}
log = get_logger("DEMO")


def worker_events(correlation_id: str, since: float) -> List[Dict[str, Any]]:
    """The worker's trace events for one correlation_id (oldest first)."""
    rows = [
        r
        for r in read_jsonl(config.WORKER_TRACE_PATH)
        if r.get("correlation_id") == correlation_id and r["ts"] >= since - 5
    ]
    return sorted(rows, key=lambda r: r["ts"])


def print_sequence(
    title: str, client: List[Dict[str, Any]], worker: List[Dict[str, Any]]
) -> bool:
    """Print the five-line flow for one request in protocol order."""
    print(f"\n  SEQUENCE: {title}")
    sent = next((e for e in client if e["event"] == "request_sent"), None)
    got = next((e for e in client if e["event"] == "response_received"), None)
    received = next((e for e in worker if e["event"] == "received"), None)
    processing = next((e for e in worker if e["event"] == "processing"), None)
    replied = next((e for e in worker if e["event"] == "reply_sent"), None)
    if sent:
        print(
            f"   1. [CLIENT] request sent      -> {sent['topic']} partition "
            f"{sent['partition']} offset {sent['offset']}  ({sent['operation']})"
        )
    if received:
        print(
            f"   2. [WORKER] request received  <- {config.REQUEST_TOPIC} partition "
            f"{received['partition']} offset {received['offset']}"
        )
    if processing:
        print(f"   3. [WORKER] processing        {processing['operation']}")
    if replied:
        print(
            f"   4. [WORKER] response sent     -> {replied['topic']} partition "
            f"{replied['partition']} offset {replied['offset']}  "
            f"(success={replied['success']})"
        )
    if got:
        print(
            f"   5. [CLIENT] response received <- {got['topic']} partition "
            f"{got['partition']} offset {got['offset']}  (success={got['success']})"
        )
    if not worker:
        print(
            "   (no worker trace found: check the worker console with "
            "'docker compose -f docker-compose.hw8.yml logs worker')"
        )
    return bool(sent and got)


async def call(
    rpc: KafkaRPC, operation: str, data: Dict[str, Any], cid: str
) -> Dict[str, Any]:
    """Send one request, print its sequence and return the response."""
    started = time.time()
    first = len(rpc.events)
    response = await rpc.request(operation, data, cid)
    await asyncio.sleep(0.3)  # let the worker's trace lines reach the file
    print_sequence(
        f"{operation} correlation_id={cid}",
        rpc.events[first:],
        worker_events(cid, started),
    )
    return response


async def demo(show_errors: bool) -> int:
    """Run the full demonstration; return a process exit code."""
    rpc = KafkaRPC(component="CLIENT", verbose=True, timeout=15)
    await rpc.start()
    summary: Dict[str, Any] = {"topics": [config.REQUEST_TOPIC, config.RESPONSE_TOPIC]}
    try:
        print("\n=== STEP 1: create one correlation_id for the CREATE request ===")
        create_cid = str(uuid.uuid4())
        log.info("correlation_id for CREATE = %s", create_cid)

        print("\n=== STEPS 2-6: CREATE request -> worker -> response ===")
        created = await call(rpc, config.CREATE_OPERATION, TRIAL, create_cid)
        print("\n  CREATE response:")
        print(json.dumps(created, indent=2))
        assert created["correlation_id"] == create_cid, "correlation_id changed!"
        if not created.get("success"):
            log.info("CREATE failed, stopping")
            return 1

        print("\n=== STEP 7: extract the generated id ===")
        entity_id = created[config.ID_FIELD]
        log.info("%s = %s", config.ID_FIELD, entity_id)

        print("\n=== STEPS 8-9: GET request with that id (its own correlation_id) ===")
        get_cid = str(uuid.uuid4())
        log.info("correlation_id for GET = %s", get_cid)
        got = await call(
            rpc, config.GET_OPERATION, {config.ID_FIELD: entity_id}, get_cid
        )

        print("\n=== STEP 10: retrieved entity and correlation_id check ===")
        print(json.dumps(got, indent=2))
        create_ok = created["correlation_id"] == create_cid
        get_ok = got["correlation_id"] == get_cid
        log.info(
            "CREATE correlation_id preserved: sent=%s received=%s -> %s",
            create_cid, created["correlation_id"], "YES" if create_ok else "NO",
        )  # fmt: skip
        log.info(
            "GET    correlation_id preserved: sent=%s received=%s -> %s",
            get_cid, got["correlation_id"], "YES" if get_ok else "NO",
        )  # fmt: skip
        same = {k: v for k, v in got.get("entity", {}).items() if k in TRIAL} == TRIAL
        log.info(
            "retrieved entity matches what was created: %s", "YES" if same else "NO"
        )
        summary.update(
            create={"correlation_id": create_cid, "response": created},
            get={"correlation_id": get_cid, "response": got},
            correlation_ids_preserved=create_ok and get_ok,
            entity_matches=same,
        )

        if show_errors:
            print("\n=== EXTRA: clean errors, each with its own correlation_id ===")
            errors = {}
            for label, op, data in (
                ("unknown operation", "DELETE_EVERYTHING", {}),
                (
                    "unknown id",
                    config.GET_OPERATION,
                    {config.ID_FIELD: "does-not-exist"},
                ),
                (
                    "invalid data",
                    config.CREATE_OPERATION,
                    {"trialTitle": "", "sponsor": "X"},
                ),
            ):
                cid = str(uuid.uuid4())
                reply = await rpc.request(op, data, cid)
                print(f"\n  {label}: sent correlation_id={cid}")
                print(json.dumps(reply, indent=2))
                errors[label] = {"sent": cid, "response": reply}
            summary["errors"] = errors

        out = config.RAW_DIR / "part1_demo.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"\nsaved {out}")
        return 0 if create_ok and get_ok and same else 1
    except RpcTimeout as exc:
        log.info(
            "TIMEOUT: no reply for %s - is the worker running?", exc.correlation_id
        )
        return 2
    finally:
        await rpc.stop()


def main() -> None:
    """Parse arguments and run the demo with the RUN_LOG tee."""
    parser = argparse.ArgumentParser(description="HW8 Part 1 demo")
    parser.add_argument(
        "--no-errors", action="store_true", help="skip the error examples"
    )
    args = parser.parse_args()
    with run_logged("Part 1 homework_demo"):
        raise SystemExit(asyncio.run(demo(not args.no_errors)))


if __name__ == "__main__":
    main()
