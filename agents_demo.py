import argparse, json, os, re, sys, time
from dataclasses import dataclass
from typing import List, Dict, Any, Iterable, Tuple

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# Optional: students can expand/modify this
STOP = {
    "the", "and", "for", "that", "with", "this", "from", "into", "than", "your", "you",
    "are", "was", "were", "have", "has", "had", "use", "used", "using", "about", "how",
    "can", "will", "more", "less", "very", "over", "under", "their", "there", "then",
    "our", "out", "on", "in", "of", "to", "by", "a", "an", "is", "it", "as",
}


# Text cleanup + extraction

def strip_code_and_md(s: str) -> str:
    """
    Remove markdown/code artifacts from model output.
    """

    # Remove fenced code markers like ```json and ```
    s = re.sub(r"```(?:json|python|text)?", "", str(s), flags=re.IGNORECASE)
    s = s.replace("```", "")

    # Remove inline backticks
    s = s.replace("`", "")

    # Normalize extra whitespace
    s = " ".join(s.split())

    return s


def extract_json_block(text: str) -> str:
    """
    Extract the first JSON object from a text response.
    If none is present, wrap cleaned text like:
    {"message": "<cleaned text>"}.
    """

    text = str(text).strip()

    # Find the first complete JSON object
    start = text.find("{")

    if start != -1:
        depth = 0
        in_string = False
        escape = False

        for i in range(start, len(text)):
            char = text[i]

            if escape:
                escape = False
                continue

            if char == "\\" and in_string:
                escape = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if not in_string:
                if char == "{":
                    depth += 1

                elif char == "}":
                    depth -= 1

                    if depth == 0:
                        return text[start:i + 1]

    # If no JSON object is found, clean the text
    cleaned = strip_code_and_md(text)

    # Wrap cleaned text inside valid JSON
    return json.dumps({"message": cleaned})


def tokens(txt: str) -> List[str]:
    """
    Tokenize text into lowercase words.
    """

    return re.findall(r"[a-z][a-z\-]+", str(txt).lower())


def ngrams(words: List[str], n: int) -> Iterable[Tuple[str, ...]]:
    """
    Yield word n-grams from a token list.
    """

    for i in range(max(0, len(words) - n + 1)):
        yield tuple(words[i:i + n])


def phrase_candidates(title: str, content: str, maxn: int = 12) -> List[str]:
    """
    Build tag candidates derived ONLY from title + content.
    """

    # Combine title and content
    combined_text = f"{title} {content}"

    # Tokenize text
    words = tokens(combined_text)

    # Remove common stop words
    filtered_words = [word for word in words if word not in STOP]

    # Store phrase frequency
    counts = {}

    # Build bigrams and trigrams
    for n in (2, 3):
        for gram in ngrams(filtered_words, n):

            phrase = " ".join(gram)

            counts[phrase] = counts.get(phrase, 0) + 1

    # Rank by frequency
    ranked_phrases = sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0])
    )

    candidates = [phrase for phrase, count in ranked_phrases]

    # Fall back to single words if needed
    if len(candidates) < maxn:

        for word in filtered_words:

            if word not in candidates:
                candidates.append(word)

            if len(candidates) >= maxn:
                break

    return candidates[:maxn]


# Output schema coercion

def coerce_reply(raw_obj: Any, title: str, content: str, strict: bool) -> Dict[str, Any]:
    """
    Coerce arbitrary model output into the required schema:

    {
        "thought": str,
        "message": str,
        "data": {
            "tags": [str, str, str],
            "summary": str,
            "issues": [str, ...]
        }
    }
    """

    # Make sure raw_obj is a dictionary
    if not isinstance(raw_obj, dict):
        raw_obj = {"message": str(raw_obj)}

    thought = strip_code_and_md(raw_obj.get("thought", ""))

    message = strip_code_and_md(
        raw_obj.get(
            "message",
            "OK — proposal reviewed; tags and summary prepared."
        )
    )

    # Limit message to 60 words
    message_words = message.split()
    message = " ".join(message_words[:60])

    if not message:
        message = "OK — proposal reviewed; tags and summary prepared."

    # Get data section
    data = raw_obj.get("data", {})

    if not isinstance(data, dict):
        data = {}

    raw_tags = data.get("tags", raw_obj.get("tags", []))
    raw_summary = data.get("summary", raw_obj.get("summary", ""))
    raw_issues = data.get("issues", raw_obj.get("issues", []))

    # Clean tags
    tags = []

    if isinstance(raw_tags, list):

        for tag in raw_tags:

            cleaned_tag = strip_code_and_md(str(tag)).strip(
                " -_,.;:[](){}\"'"
            )

            if cleaned_tag and cleaned_tag.lower() not in [
                existing.lower() for existing in tags
            ]:
                tags.append(cleaned_tag)

    # Build fallback tag candidates from title/content
    candidates = phrase_candidates(title, content, maxn=20)

    # Fill missing tags from candidates
    for candidate in candidates:

        if len(tags) >= 3:
            break

        if candidate.lower() not in [
            existing.lower() for existing in tags
        ]:
            tags.append(candidate)

    # Keep exactly 3 tags
    tags = tags[:3]

    # Strict mode: try to keep at least two multi-word tags
    if strict:

        multiword_count = sum(
            1 for tag in tags if len(tag.split()) >= 2
        )

        for candidate in candidates:

            if multiword_count >= 2:
                break

            if len(candidate.split()) < 2:
                continue

            if candidate.lower() in [
                existing.lower() for existing in tags
            ]:
                continue

            for i, tag in enumerate(tags):

                if len(tag.split()) == 1:
                    tags[i] = candidate
                    multiword_count += 1
                    break

    # Clean summary
    summary = strip_code_and_md(raw_summary)

    # Fall back to content if summary is missing
    if not summary:
        summary = strip_code_and_md(content)

    # Limit summary to 25 words
    summary_words = summary.split()
    summary = " ".join(summary_words[:25])

    # Make summary end with a period
    summary = summary.rstrip(" .!?")

    if summary:
        summary += "."

    # Normalize issues
    if isinstance(raw_issues, list):

        issues = [
            strip_code_and_md(str(issue))
            for issue in raw_issues
            if str(issue).strip()
        ]

    elif raw_issues:

        issues = [strip_code_and_md(str(raw_issues))]

    else:

        issues = []

    return {
        "thought": thought,
        "message": message,
        "data": {
            "tags": tags,
            "summary": summary,
            "issues": issues,
        },
    }


def parse_and_coerce(text: str, title: str, content: str, strict: bool) -> Dict[str, Any]:
    """
    Extract JSON, parse it, coerce it into the required schema,
    and handle parsing failures gracefully.
    """

    try:

        obj = json.loads(extract_json_block(text))

    except Exception:

        obj = {"message": strip_code_and_md(text)}

    return coerce_reply(obj, title, content, strict)


# Agent wrapper

@dataclass
class SimpleAgent:
    name: str
    system: str
    model: Any  # LangChain ChatModel

    def respond(
        self,
        conversation: List[Dict[str, str]],
        task: str,
        title: str,
        content: str,
        strict: bool,
    ) -> Dict[str, Any]:
        """
        Build prompt, run the model, and return validated output.
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system),
            ("human",
             "Task:\n{task}\n\nConversation so far:\n{history}\n\n"
             "Return ONLY one JSON object (no code fences, no markdown, no explanations). "
             "Keys: thought (string), message (non-empty, <=60 words, no code), "
             "data.tags (array of exactly 3 topical tags), "
             "data.summary (<=25 words, no ellipses), data.issues (array).\n"
             "Do not add extra text outside JSON."
            ),
        ])

        history_text = "\n".join(
            [f'{m["role"]}: {m["content"]}' for m in conversation]
        ) or "(empty)"

        chain = prompt | self.model | StrOutputParser()

        raw = chain.invoke({
            "task": task,
            "history": history_text
        })

        return parse_and_coerce(
            raw,
            title,
            content,
            strict
        )


# CLI entrypoint

def main():

    ap = argparse.ArgumentParser()

    ap.add_argument("--title", default="Your Blog Title Here")
    ap.add_argument("--content", default="Your blog post content goes here.")
    ap.add_argument("--email", default="student@example.com")

    # Use qwen3:8b by default because this is the local model we downloaded
    ap.add_argument(
        "--model",
        default=os.environ.get("SMOL_MODEL", "qwen3:8b")
    )

    ap.add_argument(
        "--base_url",
        default=os.environ.get(
            "OLLAMA_URL",
            "http://localhost:11434"
        )
    )

    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--strict", action="store_true")

    # Added for Part 3 non-determinism experiment
    ap.add_argument(
        "--temperature",
        type=float,
        default=0.0
    )

    args = ap.parse_args()

    # Initialize Ollama chat model
    try:

        llm = ChatOllama(
            model=args.model,
            temperature=args.temperature,
            base_url=args.base_url,
            num_ctx=2048,
            format="json",
        )

    except Exception:

        print(
            "Failed to initialize ChatOllama. Is Ollama running and the model available?\n"
            "Try: `ollama serve` and `ollama pull <your-model-tag>`.",
            file=sys.stderr,
        )

        raise

    # Define Planner agent
    planner = SimpleAgent(
        name="Planner",
        system=(
            "Propose exactly 3 distinct, topical tags "
            "(prefer multi-word phrases) and a one-line summary."
        ),
        model=llm,
    )

    # Define Reviewer agent
    reviewer = SimpleAgent(
        name="Reviewer",
        system=(
            "Validate: tags topical and not generic; summary ≤ 25 words; "
            "no code or markdown. If issues, list in data.issues; "
            "otherwise echo cleaned tags/summary."
        ),
        model=llm,
    )

    # Define Finalizer
    finalizer = SimpleAgent(
        name="Finalizer",
        system=(
            "Use reviewer feedback to finalize. "
            "Output exactly 3 tags in data.tags and the final summary in data.summary. "
            "Set data.issues to []."
        ),
        model=llm,
    )

    # Create task from user-provided title and content
    task = (
        f'Given title "{args.title}" and content "{args.content}", '
        f'produce exactly 3 topical tags and a one-sentence summary in your own words. '
        f'Email is {args.email}.'
    )

    transcript: List[Dict[str, str]] = []

    # Planner
    t0 = time.time()

    a = planner.respond(
        transcript,
        task,
        args.title,
        args.content,
        args.strict
    )

    t1 = time.time()

    transcript.append({
        "role": "Planner",
        "content": a.get("message", "")
    })

    print(
        f"\n--- Planner ({int((t1 - t0) * 1000)} ms) ---\n"
        f"{json.dumps(a, indent=2)}"
    )

    # Reviewer
    t0 = time.time()

    b = reviewer.respond(
        transcript,
        task,
        args.title,
        args.content,
        args.strict
    )

    t1 = time.time()

    transcript.append({
        "role": "Reviewer",
        "content": b.get("message", "")
    })

    print(
        f"\n--- Reviewer ({int((t1 - t0) * 1000)} ms) ---\n"
        f"{json.dumps(b, indent=2)}"
    )

    # Finalizer
    final = finalizer.respond(
        transcript,
        task,
        args.title,
        args.content,
        args.strict
    )

    print(
        f"\n Finalized Output \n"
        f"{json.dumps(final, indent=2)}"
    )

    # Publish package
    package = {
        "title": args.title,
        "email": args.email,
        "content": args.content,
        "agents": {
            "transcript": transcript,
            "final": final.get("data", {})
        },
        "submissionDate": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime()
        ),
    }

    print(
        f"\n Publish Package \n"
        f"{json.dumps(package, indent=2)}"
    )


if __name__ == "__main__":
    main()