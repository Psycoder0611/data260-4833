"""HW6 Part 4: file-based memory (AGENT.md + MEMORY.md), consolidation and commands."""
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from hw6 import config
from hw6.utils import parse_json_array

ChatFunction = Callable[[List[Dict[str, str]]], str]

LAST_CONSOLIDATED_PATTERN = re.compile(r"<!--\s*last-consolidated:\s*(?P<stamp>[^\s>]+)\s*-->")
ENTRY_PATTERN = re.compile(
    r"^-\s+(?P<key>[^:]+?):\s+(?P<value>.+?)(?:\s+\((?P<date>\d{4}-\d{2}-\d{2})\))?\s*$"
)
RESOLVED_HEADING = "## Resolved contradictions"

HELP_TEXT = """Available commands:
/memory   show the file-based memory (MEMORY.md) and AGENT.md summary
/compact  consolidate MEMORY.md (merge duplicates, resolve contradictions)
/dream    pull long-term facts out of the recent conversation into MEMORY.md
/help     show this help
Anything else is sent to the model with AGENT.md and MEMORY.md in the system prompt."""

DREAM_PROMPT = (
    "Read the conversation and list long-term facts worth keeping about the user or the project.\n"
    "Use short snake_case keys. Skip small talk, questions and one-off details.\n"
    "Reuse an existing key when the fact updates it.\n"
    'Return ONLY a JSON array like [{"key": "port", "value": "8333"}] with at most 5 items, '
    "or [] when nothing is worth keeping. /no_think"
)


# ------------------------------------------------------------------ loading


def load_text_file(path: Path) -> str:
    """Read a text file; return an empty string when it does not exist."""
    path = Path(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_agent_md(path: Path = config.AGENT_FILE) -> str:
    """Load AGENT.md (durable project and agent instructions)."""
    return load_text_file(path).strip()


def load_memory_md(path: Path = config.MEMORY_FILE) -> str:
    """Load MEMORY.md (durable facts learned from earlier conversations)."""
    return load_text_file(path).strip()


def build_system_prompt(agent_text: str, memory_text: str) -> str:
    """Join AGENT.md and MEMORY.md into one system prompt."""
    sections = []
    if agent_text:
        sections.append("# Instructions (AGENT.md)\n" + agent_text)
    if memory_text:
        sections.append("# Long-term memory (MEMORY.md)\n" + memory_text)
    return "\n\n".join(sections)


# ----------------------------------------------------- consolidation checks


def count_active_lines(text: str) -> int:
    """Count non-empty lines that are not inside HTML comments."""
    count = 0
    in_comment = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if not line:
            continue
        if line.startswith("<!--"):
            if "-->" not in line:
                in_comment = True
            continue
        count += 1
    return count


def read_last_consolidated(text: str) -> Optional[datetime]:
    """Read the last-consolidated timestamp comment; None when missing or invalid."""
    match = LAST_CONSOLIDATED_PATTERN.search(text)
    if not match:
        return None
    try:
        stamp = datetime.fromisoformat(match.group("stamp"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def needs_consolidation(
    text: str,
    now: Optional[datetime] = None,
    max_lines: int = config.CONSOLIDATION_LINE_LIMIT,
    max_age_hours: int = config.CONSOLIDATION_MAX_AGE_HOURS,
) -> Tuple[bool, List[str]]:
    """Return (required, reasons): more than 40 active lines or older than 24 hours."""
    now = now or datetime.now(timezone.utc)
    reasons: List[str] = []
    active = count_active_lines(text)
    if active > max_lines:
        reasons.append(f"{active} active lines (limit {max_lines})")
    stamp = read_last_consolidated(text)
    if stamp is None:
        reasons.append("no last-consolidated timestamp")
    elif now - stamp > timedelta(hours=max_age_hours):
        age_hours = round((now - stamp).total_seconds() / 3600, 1)
        reasons.append(f"last consolidation {age_hours} hours ago (limit {max_age_hours})")
    return bool(reasons), reasons


# -------------------------------------------------------------- consolidation


@dataclass
class Entry:
    """One 'key: value (date)' fact line."""

    key: str
    value: str
    date: Optional[str]
    section: str
    line_no: int


@dataclass
class ConsolidationResult:
    """Everything /compact needs to report."""

    text: str
    lines_before: int
    lines_after: int
    entries_before: int
    entries_after: int
    duplicates: List[Dict[str, object]] = field(default_factory=list)
    contradictions: List[Dict[str, object]] = field(default_factory=list)

    @property
    def incorrect(self) -> List[Dict[str, object]]:
        """Contradictions where the recency rule chose a value AGENT.md disagrees with."""
        return [item for item in self.contradictions if item["first_pass_wrong"]]


def normalize(text: str) -> str:
    """Lowercase, collapse spaces and drop quotes and a trailing period."""
    return " ".join(text.lower().split()).strip("\"'").rstrip(".")


def parse_entries(text: str) -> Tuple[List[Entry], List[str]]:
    """Return (entries, free_text_lines); skips headings, comments and the resolved section."""
    entries: List[Entry] = []
    free_lines: List[str] = []
    section = "Facts"
    in_resolved = False
    in_comment = False
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if in_comment:
            in_comment = "-->" not in line
            continue
        if line.startswith("<!--"):
            in_comment = "-->" not in line
            continue
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            in_resolved = line == RESOLVED_HEADING
            if not in_resolved:
                section = line[3:].strip()
            continue
        if in_resolved:
            continue
        match = ENTRY_PATTERN.match(line)
        if match:
            entries.append(
                Entry(match.group("key").strip(), match.group("value").strip(), match.group("date"), section, number)
            )
        else:
            free_lines.append(line)
    return entries, free_lines


def parse_fixed_facts(agent_text: str) -> Dict[str, str]:
    """Read the 'Fixed project facts' section of AGENT.md as {key: value}."""
    facts: Dict[str, str] = {}
    in_section = False
    for raw_line in agent_text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = line[3:].strip().lower() == "fixed project facts"
            continue
        if in_section:
            match = ENTRY_PATTERN.match(line)
            if match:
                facts[normalize(match.group("key"))] = match.group("value").strip()
    return facts


def pick_latest(entries: List[Entry]) -> Entry:
    """Pick the newest entry by date (missing date is oldest); later line wins ties."""
    return max(entries, key=lambda item: (item.date or "", item.line_no))


def resolve_group(key: str, entries: List[Entry], fixed: Dict[str, str]) -> Dict[str, object]:
    """Resolve one key that has more than one distinct value."""
    by_value: Dict[str, List[Entry]] = {}
    for entry in entries:
        by_value.setdefault(normalize(entry.value), []).append(entry)
    candidates = {value: pick_latest(items) for value, items in by_value.items()}
    winner = pick_latest(list(candidates.values()))
    first_pass = winner
    fixed_value = fixed.get(normalize(key))
    wrong = False
    note = "most recent value wins"
    if fixed_value is not None and normalize(winner.value) != normalize(fixed_value):
        wrong = True
        corrected = candidates.get(normalize(fixed_value))
        if corrected is not None:
            winner = corrected
            note = f'recency rule picked "{first_pass.value}" but AGENT.md says "{fixed_value}", so it was corrected'
        else:
            note = f'NEEDS REVIEW: AGENT.md says "{fixed_value}" but no stored value matches'
    rejected = [item for item in candidates.values() if item is not winner]
    return {
        "key": key,
        "winner": winner,
        "rejected": rejected,
        "first_pass_value": first_pass.value,
        "first_pass_wrong": wrong,
        "note": note,
    }


def format_entry(entry: Entry) -> str:
    """Write an entry back as a markdown bullet."""
    suffix = f" ({entry.date})" if entry.date else ""
    return f"- {entry.key}: {entry.value}{suffix}"


def consolidate(
    text: str,
    now: Optional[datetime] = None,
    fixed_facts: Optional[Dict[str, str]] = None,
) -> ConsolidationResult:
    """Merge duplicates and resolve contradictions without silently dropping anything."""
    now = now or datetime.now(timezone.utc)
    fixed = fixed_facts or {}
    entries, free_lines = parse_entries(text)
    groups: Dict[str, List[Entry]] = {}
    for entry in entries:
        groups.setdefault(normalize(entry.key), []).append(entry)

    kept: List[Entry] = []
    duplicates: List[Dict[str, object]] = []
    contradictions: List[Dict[str, object]] = []
    for key_norm, items in groups.items():
        distinct = {normalize(item.value) for item in items}
        if len(distinct) == 1:
            kept.append(pick_latest(items))
            if len(items) > 1:
                duplicates.append({"key": items[0].key, "value": items[0].value, "copies": len(items)})
            continue
        resolved = resolve_group(items[0].key, items, fixed)
        kept.append(resolved["winner"])
        contradictions.append(resolved)

    # Rebuild the file: sections in first-seen order, entries in first-seen key order.
    section_order: List[str] = []
    for entry in entries:
        if entry.section not in section_order:
            section_order.append(entry.section)
    order = {key: index for index, key in enumerate(groups)}
    stamp = now.replace(microsecond=0).isoformat()
    lines = [f"<!-- last-consolidated: {stamp} -->", "# MEMORY.md"]
    for section in section_order:
        lines += ["", f"## {section}"]
        section_entries = [item for item in kept if item.section == section]
        section_entries.sort(key=lambda item: order[normalize(item.key)])
        lines += [format_entry(item) for item in section_entries]
    for line in dict.fromkeys(free_lines):
        lines.append(line)
    if contradictions:
        lines += ["", RESOLVED_HEADING]
        for item in contradictions:
            winner = item["winner"]
            for old in item["rejected"]:
                lines.append(
                    f'- {item["key"]}: kept "{winner.value}" ({winner.date}); '
                    f'replaced "{old.value}" ({old.date}) - {item["note"]}'
                )
    new_text = "\n".join(lines) + "\n"
    return ConsolidationResult(
        text=new_text,
        lines_before=len(text.splitlines()),
        lines_after=len(new_text.splitlines()),
        entries_before=len(entries) + len(free_lines),
        entries_after=len(kept) + len(set(free_lines)),
        duplicates=duplicates,
        contradictions=contradictions,
    )


def format_compact_report(result: ConsolidationResult) -> str:
    """Describe a consolidation run in plain text (before/after counts and decisions)."""
    lines = [
        f"Entries before: {result.entries_before}   after: {result.entries_after}",
        f"Lines before:   {result.lines_before}   after: {result.lines_after}",
        f"Duplicate facts merged: {len(result.duplicates)}",
    ]
    for item in result.duplicates:
        lines.append(f'  - {item["key"]}: {item["value"]} ({item["copies"]} copies -> 1)')
    lines.append(f"Contradictions resolved: {len(result.contradictions)}")
    for item in result.contradictions:
        winner = item["winner"]
        lines.append(f'  - {item["key"]}: kept "{winner.value}" ({item["note"]})')
    wrong = result.incorrect
    lines.append(f"Resolved incorrectly by the recency rule: {len(wrong)}")
    for item in wrong:
        lines.append(f'  - {item["key"]}: first chose "{item["first_pass_value"]}" - {item["note"]}')
    return "\n".join(lines)


def compact_file(
    memory_path: Path = config.MEMORY_FILE,
    agent_path: Path = config.AGENT_FILE,
    now: Optional[datetime] = None,
) -> ConsolidationResult:
    """Consolidate MEMORY.md on disk, using AGENT.md fixed facts to audit contradictions."""
    original = load_text_file(memory_path)
    fixed = parse_fixed_facts(load_text_file(agent_path))
    result = consolidate(original, now=now, fixed_facts=fixed)
    Path(memory_path).write_text(result.text, encoding="utf-8")
    return result


# ---------------------------------------------------------------- /dream


def append_facts(memory_text: str, facts: List[Tuple[str, str]], today: Optional[date] = None) -> Tuple[str, List[str]]:
    """Add 'key: value (date)' lines before the resolved section; skip exact repeats."""
    today = today or date.today()
    existing, _ = parse_entries(memory_text)
    known = {(normalize(item.key), normalize(item.value)) for item in existing}
    lines = memory_text.rstrip("\n").splitlines()
    insert_at = len(lines)
    for index, line in enumerate(lines):
        if line.strip() == RESOLVED_HEADING:
            insert_at = index
            break
    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1
    if not lines:
        lines = ["# MEMORY.md", "", "## Facts"]
        insert_at = len(lines)
    added: List[str] = []
    new_lines: List[str] = []
    for key, value in facts:
        if (normalize(key), normalize(value)) in known:
            continue
        known.add((normalize(key), normalize(value)))
        line = f"- {key}: {value} ({today.isoformat()})"
        new_lines.append(line)
        added.append(line)
    lines[insert_at:insert_at] = new_lines
    return "\n".join(lines) + "\n", added


def dream(
    conversation: List[Dict[str, str]],
    memory_text: str,
    chat_fn: ChatFunction,
    today: Optional[date] = None,
) -> Tuple[str, List[str]]:
    """Extract long-term facts from recent conversation; return (new_memory_text, added_lines)."""
    existing, _ = parse_entries(memory_text)
    known_keys = ", ".join(sorted({item.key for item in existing})) or "(none)"
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in conversation[-20:])
    reply = chat_fn(
        [
            {"role": "system", "content": DREAM_PROMPT},
            {"role": "user", "content": f"Existing keys: {known_keys}\n\nConversation:\n{transcript}"},
        ]
    )
    facts: List[Tuple[str, str]] = []
    for item in parse_json_array(reply)[:5]:
        if isinstance(item, dict) and isinstance(item.get("key"), str) and item.get("value") is not None:
            key = re.sub(r"\s+", "_", item["key"].strip().lower())
            value = str(item["value"]).strip()
            if key and value:
                facts.append((key, value))
    return append_facts(memory_text, facts, today)


# -------------------------------------------------------------- commands


def summarize_agent_md(agent_text: str) -> str:
    """List the AGENT.md headings and how many instruction bullets each has."""
    lines = []
    heading = None
    counts: Dict[str, int] = {}
    for raw_line in agent_text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            heading = line[3:].strip()
            counts[heading] = 0
        elif line.startswith("- ") and heading:
            counts[heading] += 1
    for name, count in counts.items():
        lines.append(f"  {name}: {count} lines")
    return "\n".join(lines) if lines else "  (no sections)"


def handle_command(
    command: str,
    history: List[Dict[str, str]],
    chat_fn: ChatFunction,
    memory_path: Path = config.MEMORY_FILE,
    agent_path: Path = config.AGENT_FILE,
    now: Optional[datetime] = None,
) -> str:
    """Run /memory, /compact, /dream or /help and return the text to show."""
    name = command.strip().split()[0].lower() if command.strip() else ""
    if name == "/help":
        return HELP_TEXT
    if name == "/memory":
        memory_text = load_memory_md(memory_path)
        required, reasons = needs_consolidation(memory_text, now)
        status = "consolidation needed: " + ("yes (" + "; ".join(reasons) + ")" if required else "no")
        return (
            f"AGENT.md sections:\n{summarize_agent_md(load_agent_md(agent_path))}\n\n"
            f"MEMORY.md ({count_active_lines(memory_text)} active lines, {status}):\n{memory_text}"
        )
    if name == "/compact":
        result = compact_file(memory_path, agent_path, now)
        return "MEMORY.md consolidated.\n" + format_compact_report(result)
    if name == "/dream":
        updated, added = dream(history, load_memory_md(memory_path), chat_fn, now.date() if now else None)
        if not added:
            return "Nothing new worth remembering from the recent conversation."
        Path(memory_path).write_text(updated, encoding="utf-8")
        return "Added to MEMORY.md:\n" + "\n".join(added)
    return f"Unknown command {name}. Type /help."


def load_recent_conversation(path: Path = config.RECENT_CONVERSATION_FILE, limit: int = 20) -> List[Dict[str, str]]:
    """Read the last saved chat messages (one JSON object per line)."""
    text = load_text_file(path)
    messages = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and "role" in item and "content" in item:
            messages.append({"role": item["role"], "content": item["content"]})
    return messages[-limit:]


def save_recent_message(role: str, content: str, path: Path = config.RECENT_CONVERSATION_FILE) -> None:
    """Append one chat message to the recent-conversation file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"role": role, "content": content}, ensure_ascii=False) + "\n")
