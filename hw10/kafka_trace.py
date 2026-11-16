# ruff: noqa: E501
"""Tracing for the HW8 Planner, Writer and Reviewer without changing hw8/.

TracedRunner is the HW8 AgentRunner plus one extra step: before the first attempt on a
message it writes a queue-wait span (Kafka record timestamp -> the moment this agent
starts working on it). traced() wraps a HW8 handler so every attempt writes one stage
span (ok or error). Retries are therefore visible: a message that fails 3 times has
3 error spans, followed by a dead_letter span when the HW8 dead-letter rule fires.

The handlers, retry rule, idempotency and dead-letter behaviour are the HW8 code.

Fault injection (only for the failed-trace demo): if the inbox message carries
"inject_fault": "bad_plan", the traced Planner finishes its normal work and then
publishes an empty plan, like a planner with a bug. The HW8 Writer rejects it
(a plan must be a non-empty list), retries 3 times and dead-letters the message.
"""

import time
from typing import Any, Callable, Dict, Optional

from hw8 import config as hw8_config
from hw8.agent_base import _DEAD_LETTERED, AgentOptions, AgentRunner
from hw8.pipeline import Brain, make_planner, make_reviewer, make_writer

from hw10 import config, tracing

FAULT_FIELD = "inject_fault"
FAULT_BAD_PLAN = "bad_plan"

# last handler error per trace, so the dead_letter span can say what went wrong
_LAST_ERROR: Dict[str, str] = {}


def _attrs_for(stage: str, out: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Small stage details for the span, taken from the handler's output."""
    if not out:
        return {}
    if stage == tracing.PLANNER:
        return {"steps": len(out.get("plan") or [])}
    if stage == tracing.WRITER:
        return {"draft_words": len(str(out.get("draft", "")).split())}
    if stage == tracing.REVIEWER:
        return {"score": out.get("score"), "review_status": out.get("status")}
    return {}


def traced(stage: str, handler: Callable, component: str, path=None) -> Callable:
    """Wrap a HW8 handler so each attempt writes a span."""
    attempts: Dict[str, int] = {}

    async def wrapped(payload: Dict[str, Any], ctx: Dict[str, Any]):
        """Run the handler and record how it went."""
        cid = payload.get("correlation_id") if isinstance(payload, dict) else None
        trace_id = cid if isinstance(cid, str) and cid else "unknown"
        attempts[trace_id] = attempts.get(trace_id, 0) + 1
        attrs: Dict[str, Any] = {"attempt": attempts[trace_id]}
        started = time.time()
        try:
            out = await handler(payload, ctx)
            if (
                stage == tracing.PLANNER
                and out is not None
                and payload.get(FAULT_FIELD) == FAULT_BAD_PLAN
            ):
                out = {**out, "plan": [], "fault_injected": FAULT_BAD_PLAN}
                attrs["fault_injected"] = FAULT_BAD_PLAN
            attrs.update(_attrs_for(stage, out))
            tracing.record(
                trace_id, stage, started, time.time(), "ok", None, component, attrs, path
            )
            attempts.pop(trace_id, None)
            return out
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            _LAST_ERROR[trace_id] = message
            tracing.record(
                trace_id, stage, started, time.time(), "error", message, component, attrs, path
            )
            raise

    return wrapped


class TracedRunner(AgentRunner):
    """HW8 AgentRunner + queue-wait spans + a dead_letter span."""

    span_path = None

    async def _attempts(self, record: Any, payload, cid, ctx):
        """Write the queue-wait span, then run the normal HW8 retry loop."""
        queue_stage = tracing.TOPIC_TO_QUEUE.get(record.topic)
        stamp = getattr(record, "timestamp", None)
        if cid and queue_stage and stamp:
            tracing.record(
                cid,
                queue_stage,
                stamp / 1000.0,
                time.time(),
                "ok",
                None,
                self.label,
                {"partition": record.partition, "offset": record.offset},
                self.span_path,
            )
        result = await super()._attempts(record, payload, cid, ctx)
        if result is _DEAD_LETTERED and cid:
            now = time.time()
            tracing.record(
                cid,
                tracing.DEAD_LETTER,
                now,
                now,
                "error",
                _LAST_ERROR.get(cid, "retries exhausted"),
                self.label,
                {"failed_stage": self.options.name, "attempts": self.options.max_attempts},
                self.span_path,
            )
        return result


def build_runner(role: str, brain: Brain, bootstrap: Optional[str] = None,
                 store_path: Optional[str] = None, offset_reset: str = "latest",
                 backoff: Optional[float] = None, span_path=None) -> TracedRunner:
    """Build the traced runner for "planner", "writer" or "reviewer".

    A new consumer group starts at "latest" so the old HW8 messages are not replayed
    (each replay would cost a model call).
    """
    table = {
        "planner": (make_planner, config.INBOX_TOPIC, config.TASKS_TOPIC, config.PLANNER_GROUP, tracing.PLANNER),
        "writer": (make_writer, config.TASKS_TOPIC, config.DRAFTS_TOPIC, config.WRITER_GROUP, tracing.WRITER),
        "reviewer": (make_reviewer, config.DRAFTS_TOPIC, config.FINAL_TOPIC, config.REVIEWER_GROUP, tracing.REVIEWER),
    }
    if role not in table:
        raise ValueError(f"unknown role {role!r}")
    factory, in_topic, out_topic, group, stage = table[role]
    options = AgentOptions(
        name=role,
        in_topic=in_topic,
        out_topic=out_topic,
        group_id=group,
        offset_reset=offset_reset,
        bootstrap=bootstrap,
        store_path=store_path or str(config.IDEMPOTENCY_DB_PATH),
        backoff=hw8_config.RETRY_BACKOFF_SECONDS if backoff is None else backoff,
    )
    runner = TracedRunner(options, traced(stage, factory(brain), role.upper(), span_path))
    runner.span_path = span_path
    return runner
