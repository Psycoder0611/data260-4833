"""Offline tests for HW8 Part 1 (entity service, worker, RPC client, FastAPI).

They use the in-memory broker in hw8/fake_kafka.py, so they need no Docker and
no Ollama.  Run:  pytest -q test_hw8_part1_offline.py
"""

import asyncio
import json
import uuid
from typing import Any, Dict

import httpx
import pytest
from aiokafka import TopicPartition

from hw8 import config, entity_service, fake_kafka, kafka_io
from hw8.entity_worker import EntityWorker
from hw8.rpc_client import KafkaRPC, RpcTimeout

VALID: Dict[str, Any] = {
    "trialTitle": "Heart Study",
    "sponsor": "Acme Pharma",
    "trial_code": "CT-2026-900",
    "participant_capacity": 120,
    "submitterEmail": "pi@example.org",
    "category": "Cardiology",
}


# ------------------------------------------------------------ entity service
def test_create_returns_uuid_and_both_id_names() -> None:
    """CREATE saves the entity and returns a UUID."""
    store: Dict[str, Any] = {}
    result = entity_service.process_request(config.CREATE_OPERATION, VALID, store)
    assert result["success"] is True
    assert result[config.ID_FIELD] == result[config.GENERIC_ID_FIELD]
    assert str(uuid.UUID(result[config.ID_FIELD])) == result[config.ID_FIELD]
    assert result[config.ID_FIELD] in store


def test_get_returns_entity_and_unknown_id_is_clean_error() -> None:
    """GET works for a known id and fails cleanly for an unknown one."""
    store: Dict[str, Any] = {}
    created = entity_service.process_request(config.CREATE_OPERATION, VALID, store)
    found = entity_service.process_request(
        config.GET_OPERATION, {config.ID_FIELD: created[config.ID_FIELD]}, store
    )
    assert found["success"] is True
    assert found["entity"]["trialTitle"] == "Heart Study"
    assert found["entity"][config.ID_FIELD] == created[config.ID_FIELD]
    missing = entity_service.process_request(
        config.GET_OPERATION, {config.ID_FIELD: "nope"}, store
    )
    assert missing == {"success": False, "error": "Clinical trial not found"}
    no_id = entity_service.process_request(config.GET_OPERATION, {}, store)
    assert no_id["success"] is False and "required" in no_id["error"]


def test_get_accepts_the_generic_entity_id_name() -> None:
    """The generic spec name entity_id also works in a GET request."""
    store: Dict[str, Any] = {}
    created = entity_service.process_request(config.CREATE_OPERATION, VALID, store)
    found = entity_service.process_request(
        config.GET_OPERATION, {"entity_id": created["entity_id"]}, store
    )
    assert found["success"] is True


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"trialTitle": None}, "trialTitle is required"),
        ({"trialTitle": ""}, "trialTitle must not be empty"),
        ({"trialTitle": "   "}, "trialTitle must not be empty"),
        ({"trialTitle": "x"}, "trialTitle must be 2 to 255 characters"),
        ({"sponsor": 5}, "sponsor must be a string"),
        ({"trial_code": "ab"}, "trial_code must be 3 to 100 characters"),
        ({"participant_capacity": 0}, "participant_capacity must be at least 1"),
        ({"participant_capacity": -4}, "participant_capacity must be at least 1"),
        ({"participant_capacity": "12"}, "participant_capacity must be an integer"),
        ({"participant_capacity": True}, "participant_capacity must be an integer"),
        ({"participant_capacity": 2.5}, "participant_capacity must be an integer"),
        ({"submitterEmail": "not-an-email"}, "submitterEmail must be a valid email"),
        ({"category": ""}, "category must not be empty"),
        ({"description": 7}, "description must be a string"),
        ({"organization_id": 0}, "organization_id must be a positive integer"),
    ],
)
def test_create_rejects_bad_values(change: Dict[str, Any], expected: str) -> None:
    """Missing, empty and invalid values are rejected, and nothing is stored."""
    store: Dict[str, Any] = {}
    data = {**VALID, **change}
    for key, value in change.items():
        if value is None:
            data.pop(key)
    result = entity_service.process_request(config.CREATE_OPERATION, data, store)
    assert result["success"] is False
    assert expected in result["error"]
    assert store == {}


def test_create_rejects_non_object_and_unknown_operation() -> None:
    """A non-object payload and an unknown operation both give clean errors."""
    store: Dict[str, Any] = {}
    assert entity_service.process_request(config.CREATE_OPERATION, [], store) == {
        "success": False,
        "error": "Invalid data: data must be an object",
    }
    assert entity_service.process_request("DROP_TABLE", {}, store) == {
        "success": False,
        "error": "Unknown operation",
    }
    assert (
        entity_service.process_request(None, {}, store)["error"] == "Unknown operation"
    )


def test_each_create_gets_its_own_uuid() -> None:
    """Two creates give two different ids."""
    store: Dict[str, Any] = {}
    a = entity_service.process_request(config.CREATE_OPERATION, VALID, store)
    b = entity_service.process_request(config.CREATE_OPERATION, VALID, store)
    assert a[config.ID_FIELD] != b[config.ID_FIELD]
    assert len(store) == 2


# ------------------------------------------------------------------ over Kafka
async def _with_worker(broker: fake_kafka.FakeBroker, body: Any) -> Any:
    """Run body(worker, rpc) with a worker task and a started client."""
    worker = EntityWorker()
    task = asyncio.create_task(worker.run())
    rpc = KafkaRPC(timeout=3, verbose=False)
    await rpc.start()
    try:
        await asyncio.sleep(0.05)
        return await body(worker, rpc)
    finally:
        await rpc.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_create_then_get_over_kafka_keeps_correlation_ids(monkeypatch: Any) -> None:
    """CREATE -> GET round trip; each response echoes its own correlation_id."""
    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)

    async def body(worker: EntityWorker, rpc: KafkaRPC) -> None:
        created = await rpc.request(config.CREATE_OPERATION, VALID, "cid-create-1")
        assert created["correlation_id"] == "cid-create-1"
        assert created["success"] is True
        entity_id = created[config.ID_FIELD]
        got = await rpc.request(
            config.GET_OPERATION, {config.ID_FIELD: entity_id}, "cid-get-1"
        )
        assert got["correlation_id"] == "cid-get-1"
        assert got["entity"]["trialTitle"] == "Heart Study"
        # Both requests went to the request topic, both replies to the response topic.
        requests = broker.logs[config.REQUEST_TOPIC][0]
        responses = broker.logs[config.RESPONSE_TOPIC][0]
        assert [json.loads(r.value)["correlation_id"] for r in requests] == [
            "cid-create-1",
            "cid-get-1",
        ]
        assert [json.loads(r.value)["correlation_id"] for r in responses] == [
            "cid-create-1",
            "cid-get-1",
        ]
        sent = json.loads(requests[0].value)
        assert set(sent) == {"correlation_id", "reply_to", "operation", "data"}
        assert sent["reply_to"] == config.RESPONSE_TOPIC
        # The offset is committed only after the reply, and covers both messages.
        committed = broker.committed[(config.WORKER_GROUP, config.REQUEST_TOPIC, 0)]
        assert committed == 2

    asyncio.run(_with_worker(broker, body))


def test_error_responses_carry_the_original_correlation_id(monkeypatch: Any) -> None:
    """Unknown operation, unknown id and bad data all echo the correlation_id."""
    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)

    async def body(worker: EntityWorker, rpc: KafkaRPC) -> None:
        unknown = await rpc.request("DELETE_EVERYTHING", {}, "cid-a")
        assert unknown == {
            "correlation_id": "cid-a",
            "operation": "DELETE_EVERYTHING",
            "success": False,
            "error": "Unknown operation",
        }
        missing = await rpc.request(
            config.GET_OPERATION, {config.ID_FIELD: "x"}, "cid-b"
        )
        assert missing["correlation_id"] == "cid-b"
        assert missing["error"] == "Clinical trial not found"
        invalid = await rpc.request(config.CREATE_OPERATION, {"sponsor": ""}, "cid-c")
        assert invalid["correlation_id"] == "cid-c"
        assert invalid["success"] is False
        assert worker.store == {}

    asyncio.run(_with_worker(broker, body))


def test_bad_envelopes_get_clean_errors(monkeypatch: Any) -> None:
    """Missing reply_to, missing data, foreign reply_to and non-JSON are handled."""
    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)

    async def body(worker: EntityWorker, rpc: KafkaRPC) -> None:
        producer = kafka_io.make_producer()
        await producer.start()

        async def send(message: Any) -> None:
            raw = (
                message if isinstance(message, bytes) else json.dumps(message).encode()
            )
            await producer.send_and_wait(config.REQUEST_TOPIC, raw)

        await send({"correlation_id": "e1", "operation": "X", "data": {}})
        await send(
            {
                "correlation_id": "e2",
                "reply_to": "s4833_entity_responses",
                "operation": config.GET_OPERATION,
            }
        )
        await send(
            {
                "correlation_id": "e3",
                "reply_to": "other_topic",
                "operation": config.GET_OPERATION,
                "data": {},
            }
        )
        await send(b"this is not json")
        await asyncio.sleep(0.5)
        replies = [json.loads(r.value) for r in broker.logs[config.RESPONSE_TOPIC][0]]
        by_id = {r["correlation_id"]: r for r in replies}
        assert by_id["e1"]["error"] == "reply_to is required"
        assert by_id["e2"]["error"] == "data is required"
        assert by_id["e3"]["error"] == "Invalid reply_to topic"
        bad = [r for r in replies if r["correlation_id"] is None]
        assert bad and "Bad message" in bad[0]["error"]
        assert broker.committed[(config.WORKER_GROUP, config.REQUEST_TOPIC, 0)] == 4
        await producer.stop()

    asyncio.run(_with_worker(broker, body))


def test_repeated_correlation_id_does_not_create_a_second_entity(
    monkeypatch: Any,
) -> None:
    """A redelivered CREATE gets the saved response; only one entity exists."""
    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)

    async def body(worker: EntityWorker, rpc: KafkaRPC) -> None:
        first = await rpc.request(config.CREATE_OPERATION, VALID, "dup-1")
        # Put the very same request on the topic again (a duplicate delivery).
        producer = kafka_io.make_producer()
        await producer.start()
        again = json.loads(broker.logs[config.REQUEST_TOPIC][0][0].value)
        await producer.send_and_wait(config.REQUEST_TOPIC, kafka_io.dumps(again))
        await asyncio.sleep(0.4)
        await producer.stop()
        assert len(worker.store) == 1
        replies = [json.loads(r.value) for r in broker.logs[config.RESPONSE_TOPIC][0]]
        assert len(replies) == 2
        assert replies[1][config.ID_FIELD] == first[config.ID_FIELD]

    asyncio.run(_with_worker(broker, body))


def test_client_times_out_when_no_worker_runs(monkeypatch: Any) -> None:
    """Without a worker the client raises RpcTimeout with the correlation_id."""
    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)

    async def run() -> None:
        rpc = KafkaRPC(timeout=0.3, verbose=False)
        await rpc.start()
        try:
            with pytest.raises(RpcTimeout) as info:
                await rpc.request(config.GET_OPERATION, {}, "lonely")
            assert info.value.correlation_id == "lonely"
            assert rpc.pending == {}
        finally:
            await rpc.stop()

    asyncio.run(run())


def test_worker_trace_file_records_the_three_steps(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """With tracing on, the worker writes received, processing and reply_sent."""
    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)
    trace = tmp_path / "trace.jsonl"

    async def run() -> None:
        worker = EntityWorker(trace_path=trace)
        task = asyncio.create_task(worker.run())
        rpc = KafkaRPC(timeout=3, verbose=False)
        await rpc.start()
        await rpc.request(config.CREATE_OPERATION, VALID, "traced-1")
        await rpc.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [e["event"] for e in events] == ["received", "processing", "reply_sent"]
    assert {e["correlation_id"] for e in events} == {"traced-1"}


# ------------------------------------------------------------------- FastAPI
def test_fastapi_kafka_and_direct_endpoints(monkeypatch: Any) -> None:
    """Both endpoints answer; the Kafka one goes through the worker."""
    from hw8 import api

    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)
    api.direct_store.clear()

    async def run() -> None:
        worker = EntityWorker()
        task = asyncio.create_task(worker.run())
        async with api.app.router.lifespan_context(api.app):
            transport = httpx.ASGITransport(app=api.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://t"
            ) as client:
                payload = {"operation": config.CREATE_OPERATION, "data": VALID}
                via_kafka = await client.post(
                    "/api/hw8/entity",
                    json=payload,
                    headers={"X-Correlation-ID": "api-1"},
                )
                assert via_kafka.status_code == 200
                body = via_kafka.json()
                assert body["success"] is True and body["correlation_id"] == "api-1"
                assert body[config.ID_FIELD] in worker.store
                direct = await client.post("/api/hw8/entity-direct", json=payload)
                assert direct.status_code == 200
                assert direct.json()["success"] is True
                assert len(api.direct_store) == 1
                assert len(worker.store) == 1  # the direct call never touched Kafka
                got = await client.post(
                    "/api/hw8/entity",
                    json={
                        "operation": config.GET_OPERATION,
                        "data": {config.ID_FIELD: body[config.ID_FIELD]},
                    },
                )
                assert got.json()["entity"]["sponsor"] == "Acme Pharma"
                bad = await client.post("/api/hw8/entity", json={"data": {}})
                assert bad.status_code == 422
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())


def test_fastapi_returns_504_when_worker_is_down(monkeypatch: Any) -> None:
    """With no worker the Kafka endpoint answers 504 and keeps the correlation_id."""
    from hw8 import api

    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)
    monkeypatch.setattr(api.rpc, "timeout", 0.3)

    async def run() -> None:
        async with api.app.router.lifespan_context(api.app):
            transport = httpx.ASGITransport(app=api.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://t"
            ) as client:
                reply = await client.post(
                    "/api/hw8/entity",
                    json={"operation": config.GET_OPERATION, "data": {}},
                    headers={"X-Correlation-ID": "no-worker"},
                )
                assert reply.status_code == 504
                assert reply.json()["correlation_id"] == "no-worker"

    asyncio.run(run())


def test_topic_names_follow_the_prefix() -> None:
    """Exactly two Part 1 topics, both PREFIX-prefixed."""
    assert config.REQUEST_TOPIC == "s4833_entity_requests"
    assert config.RESPONSE_TOPIC == "s4833_entity_responses"
    assert config.PORT_BASE == 8000 + (config.SID4 % 900)
    assert config.VERIFY_SEED == 260000 + config.SID4
    assert config.DOMAIN_ID == config.SID4 % 8
    assert TopicPartition(config.TASKS_TOPIC, 1)
    assert config.TOPIC_PARTITIONS[config.TASKS_TOPIC] == 2


# ----------------------------------------------------------- homework_demo.py
def test_homework_demo_runs_the_full_flow(
    monkeypatch: Any, tmp_path: Any, capsys: Any
) -> None:
    """The demo does CREATE -> GET, prints the sequences and keeps the ids."""
    import homework_demo

    broker = fake_kafka.FakeBroker()
    fake_kafka.install(monkeypatch, broker)
    trace = tmp_path / "worker_trace.jsonl"
    monkeypatch.setattr(config, "WORKER_TRACE_PATH", trace)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)

    async def run() -> int:
        worker = EntityWorker(trace_path=trace)
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.05)
        try:
            return await homework_demo.demo(show_errors=True)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    assert asyncio.run(run()) == 0
    output = capsys.readouterr().out
    assert output.count("1. [CLIENT] request sent") == 2  # CREATE and GET
    assert output.count("2. [WORKER] request received") == 2
    assert output.count("3. [WORKER] processing") == 2
    assert output.count("4. [WORKER] response sent") == 2
    assert output.count("5. [CLIENT] response received") == 2
    assert "CREATE correlation_id preserved" in output and "-> YES" in output
    assert "Clinical trial not found" in output and "Unknown operation" in output
    summary = json.loads((tmp_path / "part1_demo.json").read_text())
    assert summary["correlation_ids_preserved"] is True
    assert summary["entity_matches"] is True
