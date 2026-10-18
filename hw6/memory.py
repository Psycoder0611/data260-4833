"""HW6 Parts 2 and 3: short-term, long-term (summary) and episodic memory in MongoDB."""
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from hw6 import config, llm
from hw6.mongo import get_collection
from hw6.utils import clean_doc, now_utc, parse_json_array

logger = logging.getLogger("hw6.memory")

SYSTEM_PRIMER = (
    "You are a friendly assistant with a memory of the user. "
    "Use the memory notes below when they help. "
    "Answer in 1-3 short sentences. If you do not know something about the user, say so. "
    "/no_think"
)

SUMMARY_PROMPT = (
    "Update the running summary of this conversation.\n"
    "Write at most 6 short bullet lines, each starting with '- '.\n"
    "Keep names, dates, numbers and preferences exactly as the user said them.\n"
    "No introduction and no closing line. /no_think"
)

LIFETIME_PROMPT = (
    "Merge these notes into one lifetime summary about the user.\n"
    "Write at most 8 short bullet lines, each starting with '- '.\n"
    "Keep names, dates, numbers and preferences exactly. Drop repeats.\n"
    "No introduction and no closing line. /no_think"
)

EXTRACT_PROMPT = (
    "Extract up to 3 short facts worth remembering from the USER message below.\n"
    "Facts must be about the user: who they are, plans, preferences, pets, people, dates, numbers. "
    "Always keep names (a pet, a neighbour, a co-author) and who does what.\n"
    "Each fact is under 15 words and stands alone. Skip small talk and questions.\n"
    'Return ONLY a JSON array like [{"fact": "...", "importance": 0.7}] '
    "(importance from 0.0 to 1.0). Return [] when there is nothing to remember. /no_think"
)


@dataclass
class MemoryConfig:
    """Settings that change how much memory goes into each prompt."""

    short_term_n: int = config.SHORT_TERM_N
    summarize_every: int = config.SUMMARIZE_EVERY_USER_MSGS
    top_k: int = config.EPISODIC_TOP_K
    policy: str = "none"  # "none" or "compress_older"
    keep_recent: int = config.KEEP_RECENT_VERBATIM
    lifetime_every: int = config.LIFETIME_EVERY_SESSION_SUMMARIES
    max_facts: int = 3


def new_usage() -> Dict[str, Any]:
    """Return an empty counter for tokens spent on background calls."""
    return {"aux_prompt_tokens": 0, "aux_completion_tokens": 0}


def add_aux(usage: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Add one background model call to the aux token counters."""
    usage["aux_prompt_tokens"] += result.get("input_tokens", 0)
    usage["aux_completion_tokens"] += result.get("output_tokens", 0)


# ---------------------------------------------------------------- messages


def save_message(user_id: str, session_id: str, role: str, content: str) -> Dict[str, Any]:
    """Insert one chat message and return the stored document."""
    document = {
        "user_id": user_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": now_utc(),
    }
    result = get_collection(config.MESSAGES_COLLECTION).insert_one(document)
    document["_id"] = result.inserted_id
    return document


def load_short_term(user_id: str, session_id: str, n: int, exclude_id: Any = None) -> List[Dict[str, Any]]:
    """Return the last n messages of a session in time order (optionally skipping one id)."""
    cursor = (
        get_collection(config.MESSAGES_COLLECTION)
        .find({"user_id": user_id, "session_id": session_id})
        .sort([("created_at", -1), ("_id", -1)])
        .limit(n + 1)
    )
    docs = [doc for doc in cursor if exclude_id is None or doc["_id"] != exclude_id]
    docs = docs[:n]
    docs.reverse()
    return docs


def count_user_messages(user_id: str, session_id: str) -> int:
    """Count the user-role messages in one session."""
    return get_collection(config.MESSAGES_COLLECTION).count_documents(
        {"user_id": user_id, "session_id": session_id, "role": "user"}
    )


# --------------------------------------------------------------- summaries


def latest_summary(user_id: str, scope: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return the newest summary of a scope ('session' or 'user'), or None."""
    query: Dict[str, Any] = {"user_id": user_id, "scope": scope}
    if scope == "session" and session_id is not None:
        query["session_id"] = session_id
    return get_collection(config.SUMMARIES_COLLECTION).find_one(
        query, sort=[("created_at", -1), ("_id", -1)]
    )


def save_summary(user_id: str, session_id: Optional[str], scope: str, text: str) -> Dict[str, Any]:
    """Insert a summary document (lifetime summaries use session_id=None)."""
    document = {
        "user_id": user_id,
        "session_id": session_id,
        "scope": scope,
        "text": text,
        "created_at": now_utc(),
    }
    result = get_collection(config.SUMMARIES_COLLECTION).insert_one(document)
    document["_id"] = result.inserted_id
    return document


def summarize_session(user_id: str, session_id: str, cfg: MemoryConfig, usage: Dict[str, Any]) -> str:
    """Write a new session summary from the previous one plus the latest messages."""
    recent = load_short_term(user_id, session_id, cfg.summarize_every * 2)
    previous = latest_summary(user_id, "session", session_id)
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
    body = (
        f"Previous summary:\n{previous['text'] if previous else '(none yet)'}\n\n"
        f"New messages:\n{transcript}"
    )
    result = llm.chat(
        [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": body},
        ]
    )
    add_aux(usage, result)
    save_summary(user_id, session_id, "session", result["content"])
    return result["content"]


def condense_lifetime(user_id: str, cfg: MemoryConfig, usage: Dict[str, Any]) -> Optional[str]:
    """Condense session summaries into a lifetime summary once enough have piled up."""
    summaries = get_collection(config.SUMMARIES_COLLECTION)
    last_lifetime = latest_summary(user_id, "user")
    query: Dict[str, Any] = {"user_id": user_id, "scope": "session"}
    if last_lifetime is not None:
        query["_id"] = {"$gt": last_lifetime["_id"]}
    fresh = list(summaries.find(query).sort([("created_at", 1), ("_id", 1)]))
    if len(fresh) < cfg.lifetime_every:
        return None
    parts = []
    if last_lifetime is not None:
        parts.append(f"Earlier lifetime summary:\n{last_lifetime['text']}")
    for index, doc in enumerate(fresh, start=1):
        parts.append(f"Session summary {index}:\n{doc['text']}")
    result = llm.chat(
        [
            {"role": "system", "content": LIFETIME_PROMPT},
            {"role": "user", "content": "\n\n".join(parts)},
        ]
    )
    add_aux(usage, result)
    save_summary(user_id, None, "user", result["content"])
    return result["content"]


# --------------------------------------------------------------- episodes


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Return the cosine similarity of two vectors (0.0 if either is all zeros)."""
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if norm == 0.0:
        return 0.0
    return float(np.dot(va, vb) / norm)


def extract_episodes(message: str, cfg: MemoryConfig, usage: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ask the model for up to 3 short facts with importance scores."""
    result = llm.chat(
        [
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": f'USER message: """{message}"""'},
        ]
    )
    add_aux(usage, result)
    facts: List[Dict[str, Any]] = []
    seen = set()
    for item in parse_json_array(result["content"]):
        if not isinstance(item, dict) or not isinstance(item.get("fact"), str):
            continue
        fact = item["fact"].strip()[:200]
        key = fact.lower()
        if not fact or key in seen:
            continue
        try:
            importance = min(1.0, max(0.0, float(item.get("importance", 0.5))))
        except (TypeError, ValueError):
            importance = 0.5
        seen.add(key)
        facts.append({"fact": fact, "importance": importance})
    return facts[: cfg.max_facts]


def store_episodes(user_id: str, session_id: str, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Embed each fact and store it in the episodes collection."""
    stored = []
    for item in facts:
        document = {
            "user_id": user_id,
            "session_id": session_id,
            "fact": item["fact"],
            "importance": float(item["importance"]),
            "embedding": llm.embed(item["fact"]),
            "created_at": now_utc(),
        }
        get_collection(config.EPISODES_COLLECTION).insert_one(document)
        stored.append({"fact": document["fact"], "importance": document["importance"]})
    return stored


def retrieve_episodes(user_id: str, query: str, top_k: int) -> List[Dict[str, Any]]:
    """Return the top_k stored facts closest (cosine) to the query text."""
    docs = list(get_collection(config.EPISODES_COLLECTION).find({"user_id": user_id}))
    if not docs or top_k <= 0:
        return []
    try:
        query_vector = llm.embed(query)
    except llm.ModelUnavailableError as exc:
        logger.warning("Episodic retrieval skipped: %s", exc)
        return []
    scored = []
    for doc in docs:
        vector = doc.get("embedding") or []
        if len(vector) != len(query_vector):
            continue
        scored.append(
            {
                "fact": doc["fact"],
                "importance": doc.get("importance", 0.5),
                "score": round(cosine_similarity(query_vector, vector), 4),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------- prompt building


def digest_older(messages: List[Dict[str, Any]], max_chars: int = 120) -> str:
    """Compress older messages: drop assistant replies, shorten user lines to bullets."""
    lines = []
    for message in messages:
        if message["role"] != "user":
            continue
        text = " ".join(message["content"].split())
        if len(text) > max_chars:
            text = text[: max_chars - 3].rstrip() + "..."
        lines.append(f"- {text}")
    return "\n".join(lines)


def apply_policy(window: List[Dict[str, Any]], cfg: MemoryConfig) -> Tuple[str, List[Dict[str, Any]]]:
    """Return (digest_text, verbatim_messages) for the chosen memory-saving policy."""
    if cfg.policy != "compress_older" or len(window) <= cfg.keep_recent:
        return "", window
    older = window[: -cfg.keep_recent]
    recent = window[-cfg.keep_recent :]
    return digest_older(older), recent


def build_messages(
    message: str,
    window: List[Dict[str, Any]],
    session_summary: Optional[str],
    lifetime_summary: Optional[str],
    episodes: List[Dict[str, Any]],
    digest: str = "",
) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """Assemble the model prompt and the text of each part (for token accounting)."""
    long_term = ""
    if lifetime_summary:
        long_term += f"\n\n## Lifetime summary\n{lifetime_summary}"
    if session_summary:
        long_term += f"\n\n## Session summary\n{session_summary}"
    short_term_note = f"\n\n## Earlier in this chat (condensed)\n{digest}" if digest else ""
    system_text = SYSTEM_PRIMER + long_term + short_term_note
    episodic = ""
    if episodes:
        facts = "\n".join(f"- {item['fact']}" for item in episodes)
        episodic = f"\n\n(Remembered facts that may help:\n{facts})"
    messages = [{"role": "system", "content": system_text}]
    messages += [{"role": m["role"], "content": m["content"]} for m in window]
    messages.append({"role": "user", "content": message + episodic})
    parts = {
        "primer": SYSTEM_PRIMER,
        "long_term": long_term.strip(),
        "short_term": "\n".join(
            [short_term_note.strip()] + [f"{m['role']}: {m['content']}" for m in window]
        ).strip(),
        "episodic": episodic.strip(),
        "current": message,
    }
    return messages, parts


def allocate_tokens(parts: Dict[str, str], prompt_tokens: int) -> Dict[str, int]:
    """Split the real prompt token count across the parts in proportion to their text length."""
    sizes = {name: max(len(text), 0) for name, text in parts.items()}
    total = sum(sizes.values()) or 1
    if prompt_tokens <= 0:
        prompt_tokens = max(1, total // 4)
    allocated = {name: int(round(prompt_tokens * size / total)) for name, size in sizes.items()}
    others = sum(value for name, value in allocated.items() if name != "current")
    allocated["current"] = max(0, prompt_tokens - others)
    return {
        "system_primer_tokens": allocated["primer"],
        "long_term_tokens": allocated["long_term"],
        "short_term_tokens": allocated["short_term"],
        "episodic_tokens": allocated["episodic"],
        "current_message_tokens": allocated["current"],
    }


# -------------------------------------------------------------- chat turn


def prepare_context(user_id: str, session_id: str, message: str, cfg: MemoryConfig, current_id: Any = None) -> Dict[str, Any]:
    """Load everything the prompt needs: window, summaries and episodic facts."""
    window = load_short_term(user_id, session_id, cfg.short_term_n, exclude_id=current_id)
    session_doc = latest_summary(user_id, "session", session_id)
    lifetime_doc = latest_summary(user_id, "user")
    episodes = retrieve_episodes(user_id, message, cfg.top_k)
    digest, verbatim = apply_policy(window, cfg)
    return {
        "window": verbatim,
        "digest": digest,
        "session_summary": session_doc["text"] if session_doc else None,
        "lifetime_summary": lifetime_doc["text"] if lifetime_doc else None,
        "episodes": episodes,
    }


def after_reply(user_id: str, session_id: str, message: str, cfg: MemoryConfig, usage: Dict[str, Any]) -> Dict[str, Any]:
    """Extract episodes and refresh summaries when the schedule says so."""
    facts = extract_episodes(message, cfg, usage)
    stored = store_episodes(user_id, session_id, facts)
    session_text = lifetime_text = None
    if count_user_messages(user_id, session_id) % cfg.summarize_every == 0:
        session_text = summarize_session(user_id, session_id, cfg, usage)
        lifetime_text = condense_lifetime(user_id, cfg, usage)
    return {
        "episodes_added": stored,
        "session_summary_created": session_text,
        "lifetime_summary_created": lifetime_text,
    }


def chat_turn(
    user_id: str,
    session_id: Optional[str],
    message: str,
    cfg: Optional[MemoryConfig] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Run one full /api/chat turn and return the reply plus what memory was used."""
    cfg = cfg or MemoryConfig()
    session_id = session_id or f"s-{uuid.uuid4().hex[:8]}"
    started = time.perf_counter()
    usage = new_usage()
    current = save_message(user_id, session_id, "user", message) if persist else None
    context = prepare_context(user_id, session_id, message, cfg, current["_id"] if current else None)
    messages, parts = build_messages(
        message,
        context["window"],
        context["session_summary"],
        context["lifetime_summary"],
        context["episodes"],
        context["digest"],
    )
    result = llm.chat(messages)
    reply = result["content"]
    new_memory: Dict[str, Any] = {"episodes_added": [], "session_summary_created": None, "lifetime_summary_created": None}
    if persist:
        save_message(user_id, session_id, "assistant", reply)
        new_memory = after_reply(user_id, session_id, message, cfg, usage)
    usage.update(allocate_tokens(parts, result["input_tokens"]))
    usage.update(
        {
            "prompt_tokens": result["input_tokens"],
            "completion_tokens": result["output_tokens"],
            "model_latency_ms": result["latency_ms"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    )
    return {
        "reply": reply,
        "user_id": user_id,
        "session_id": session_id,
        "memory_used": {
            "short_term_count": len(context["window"]),
            "short_term_messages": [{"role": m["role"], "content": m["content"]} for m in context["window"]],
            "compressed_digest": context["digest"] or None,
            "session_summary": context["session_summary"],
            "lifetime_summary": context["lifetime_summary"],
            "episodic_facts": context["episodes"],
        },
        "new_memory": new_memory,
        "usage": usage,
        "config": asdict(cfg),
    }


# ------------------------------------------------------- memory and report


def get_memory(user_id: str) -> Dict[str, Any]:
    """Return last 16 messages, latest summaries and last 20 episodic facts."""
    messages = list(
        get_collection(config.MESSAGES_COLLECTION)
        .find({"user_id": user_id})
        .sort([("created_at", -1), ("_id", -1)])
        .limit(16)
    )
    messages.reverse()
    session_doc = latest_summary(user_id, "session")
    lifetime_doc = latest_summary(user_id, "user")
    episodes = list(
        get_collection(config.EPISODES_COLLECTION)
        .find({"user_id": user_id}, {"embedding": 0})
        .sort([("created_at", -1), ("_id", -1)])
        .limit(20)
    )
    return {
        "user_id": user_id,
        "messages": [clean_doc(doc) for doc in messages],
        "session_summary": clean_doc(session_doc) if session_doc else None,
        "lifetime_summary": clean_doc(lifetime_doc) if lifetime_doc else None,
        "episodes": [clean_doc(doc) for doc in episodes],
    }


def get_aggregate(user_id: str, recent_summaries: int = 5) -> Dict[str, Any]:
    """Return daily message counts (MongoDB aggregation) and the newest summaries."""
    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "messages": {"$sum": 1},
                "user_messages": {"$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    daily = [
        {"date": row["_id"], "messages": row["messages"], "user_messages": row["user_messages"]}
        for row in get_collection(config.MESSAGES_COLLECTION).aggregate(pipeline)
    ]
    summaries = list(
        get_collection(config.SUMMARIES_COLLECTION)
        .find({"user_id": user_id})
        .sort([("created_at", -1), ("_id", -1)])
        .limit(recent_summaries)
    )
    return {
        "user_id": user_id,
        "daily_message_counts": daily,
        "recent_summaries": [clean_doc(doc) for doc in summaries],
    }
