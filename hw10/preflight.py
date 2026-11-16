# ruff: noqa: E501
"""Quick checks before a long run, so a missing service fails in seconds, not minutes."""

from typing import List

import requests

from hw8 import config as hw8_config

from hw10 import config


def check_ollama(models: List[str]) -> List[str]:
    """Problems with the local Ollama server or its models (empty list = fine)."""
    try:
        tags = requests.get(f"{config.JUDGE_URL}/api/tags", timeout=5).json()
    except Exception as exc:
        return [f"Ollama is not reachable at {config.JUDGE_URL}: {exc}"]
    have = {m["name"] for m in tags.get("models", [])}
    bases = {n.split(":")[0] for n in have}
    return [f"Ollama model {m} is not installed (ollama pull {m})" for m in models if m not in have and m.split(":")[0] not in bases]


def check_redis() -> List[str]:
    """Problems with Redis Stack."""
    try:
        from hw9.runtime import make_binary_redis

        make_binary_redis()
        return []
    except Exception as exc:
        return [f"Redis is not reachable (docker compose -f docker-compose.hw9.yml up -d): {exc}"]


async def check_kafka(need_agents: bool) -> List[str]:
    """Problems with Kafka, and (optionally) with the three HW10 traced agents."""
    from aiokafka.admin import AIOKafkaAdminClient

    admin = AIOKafkaAdminClient(bootstrap_servers=hw8_config.BOOTSTRAP_SERVERS, request_timeout_ms=8000)
    try:
        await admin.start()
    except Exception as exc:
        return [f"Kafka is not reachable at {hw8_config.BOOTSTRAP_SERVERS}: {exc}"]
    problems: List[str] = []
    try:
        topics = set(await admin.list_topics())
        problems += [f"topic {t} is missing" for t in hw8_config.TOPIC_PARTITIONS if t not in topics]
        # The admin API of aiokafka 0.14 cannot decode the consumer-group listing of this
        # Kafka version, so the agents are not checked here; a missing agent shows up as a
        # request timeout (REQUEST_TIMEOUT_SECONDS) with no queue_inbox span.
    finally:
        await admin.close()
    return problems


async def run_checks(need_agents: bool, need_judge: bool = True, need_cache: bool = True) -> bool:
    """Print every problem; return True when the run can start."""
    problems: List[str] = []
    models = ["nomic-embed-text"] if need_cache else []
    if need_judge:
        models.append(config.JUDGE_MODEL)
    problems += check_ollama(models)
    if need_cache:
        problems += check_redis()
    problems += await check_kafka(need_agents)
    for line in problems:
        print("PREFLIGHT FAIL:", line)
    if not problems:
        print("Preflight OK: Kafka topics, Redis and Ollama are reachable.")
    return not problems
