# ruff: noqa: E501
"""GEval judge on a LOCAL model (Ollama qwen3:8b). No hosted API is ever called.

OllamaJudge is a DeepEval custom model: DeepEval's GEval builds the judging prompt from
the criteria and calls generate(); this class sends it to Ollama with temperature 0 and
the fixed seed, asks for JSON that matches DeepEval's schema, and returns it.

Bounds: one HTTP call has a connect and a read timeout (JUDGE_CALL_TIMEOUT); one whole
metric runs in a worker thread and is abandoned after METRIC_TIMEOUT. A judge that is
down, slow or answers with broken JSON gives a result with score None and a status
("judge_error", "timeout", "bad_judge_output") instead of hanging or raising.

Scale: GEval is given a 5-band rubric over its internal 0-10 range
(0-2 -> 1, 3-4 -> 2, 5-6 -> 3, 7-8 -> 4, 9-10 -> 5), so the reported score is an
integer 1-5, the same scale as the human labels.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable, Dict, List, Optional

import requests

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")

from deepeval.metrics import GEval  # noqa: E402
from deepeval.metrics.g_eval.utils import Rubric  # noqa: E402
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

try:  # name differs between DeepEval versions
    from deepeval.test_case import SingleTurnParams as Params
except ImportError:  # pragma: no cover
    from deepeval.test_case import LLMTestCaseParams as Params

from hw10 import config  # noqa: E402

THINK = re.compile(r"<think>.*?</think>", re.DOTALL)

# 1-5 band for the judge's internal 0-10 score
BANDS = [(0, 2, 1), (3, 4, 2), (5, 6, 3), (7, 8, 4), (9, 10, 5)]


class JudgeError(RuntimeError):
    """The local judge could not be reached or returned unusable output."""


def band_for(score10: float) -> int:
    """Map GEval's 0-10 score to the 1-5 scale used everywhere in HW10."""
    value = int(round(score10))
    for low, high, band in BANDS:
        if low <= value <= high:
            return band
    return 5 if value > 10 else 1


class OllamaJudge(DeepEvalBaseLLM):
    """DeepEval model wrapper around a local Ollama chat call."""

    def __init__(
        self,
        model: str = config.JUDGE_MODEL,
        base_url: str = config.JUDGE_URL,
        call_timeout: float = config.JUDGE_CALL_TIMEOUT,
        chat_fn: Optional[Callable[[str, Optional[dict]], str]] = None,
    ) -> None:
        """chat_fn replaces the HTTP call (offline tests only)."""
        self.model_name = model
        self.base_url = base_url.rstrip("/")
        self.call_timeout = call_timeout
        self.chat_fn = chat_fn
        self.calls = 0
        super().__init__(model)

    def load_model(self, *args: Any, **kwargs: Any) -> "OllamaJudge":
        """Nothing to load: the model lives in the Ollama server."""
        return self

    def get_model_name(self, *args: Any, **kwargs: Any) -> str:
        """Name shown in DeepEval logs."""
        return f"ollama/{self.model_name}"

    def supports_structured_outputs(self) -> bool:
        """DeepEval passes a schema; Ollama's format option enforces it."""
        return True

    def _chat(self, prompt: str, schema_json: Optional[dict]) -> str:
        """One local chat call; returns the reply text."""
        self.calls += 1
        if self.chat_fn is not None:
            return self.chat_fn(prompt, schema_json)
        body = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt + " /no_think"}],
            "stream": False,
            "think": False,
            "format": schema_json or "json",
            "options": {
                "temperature": config.JUDGE_TEMPERATURE,
                "seed": config.JUDGE_SEED,
                "num_predict": config.JUDGE_MAX_TOKENS,
            },
        }
        try:
            reply = requests.post(
                f"{self.base_url}/api/chat",
                json=body,
                timeout=(5, self.call_timeout),
            )
            reply.raise_for_status()
            return THINK.sub("", reply.json()["message"]["content"]).strip()
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise JudgeError(f"local judge call failed: {exc}") from exc

    def generate(self, prompt: str, schema: Any = None, *args: Any, **kwargs: Any):
        """Return a string, or an instance of `schema` when DeepEval passes one."""
        schema_json = schema.model_json_schema() if schema is not None else None
        text = self._chat(prompt, schema_json)
        if schema is None:
            return text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise JudgeError(f"judge reply has no JSON object: {text[:120]!r}")
        try:
            return schema.model_validate(json.loads(match.group(0)))
        except Exception as exc:
            raise JudgeError(f"judge JSON does not match the schema: {exc}") from exc

    async def a_generate(self, prompt: str, schema: Any = None, *args: Any, **kwargs: Any):
        """Async variant; the work is the same blocking call."""
        import asyncio

        return await asyncio.to_thread(self.generate, prompt, schema)


# ---------------------------------------------------------------- criteria
RUBRIC = [
    Rubric(score_range=(0, 2), expected_outcome="Unhelpful: wrong, off-topic or empty."),
    Rubric(score_range=(3, 4), expected_outcome="Mostly unhelpful: major gaps or clear errors."),
    Rubric(score_range=(5, 6), expected_outcome="Partly helpful: relevant but incomplete, vague or with small errors."),
    Rubric(score_range=(7, 8), expected_outcome="Helpful and correct for the question, minor gaps only."),
    Rubric(score_range=(9, 10), expected_outcome="Fully helpful: correct, clear and complete for the question."),
]
SCORE_STEP = "Choose the rubric band that fits best and answer with a whole number from 0 to 10 (this is a 0-10 score, not a 1-5 score)."

PLAN_STEPS = [
    "Read the question and the plan. The plan is a short list of steps that another agent will follow to answer the question.",
    "Check that every step is relevant to the question and that together the steps would lead to a complete answer.",
    "Check that the steps are specific, in a sensible order, and do not invent facts or ask for things the question does not need.",
    "Penalise vague, repeated, off-topic or missing steps.",
    SCORE_STEP,
]
HELPFUL_STEPS = [
    "Read the question and the answer.",
    "Check that the answer addresses what the question asks directly, in plain language, for someone using a clinical trial listings service.",
    "Check that facts given in the question (for example listing details) are used correctly, and that the answer does not invent specific facts such as numbers, names or eligibility rules that are not in the question.",
    "Penalise answers that are off-topic, vague, padded, incomplete, or confidently wrong; reward answers that are accurate, clear and complete without padding.",
    SCORE_STEP,
]

METRICS = {
    "plan_quality": ("Plan Quality", PLAN_STEPS),
    "helpfulness": ("Helpfulness", HELPFUL_STEPS),
}


def build_metric(kind: str, judge: DeepEvalBaseLLM) -> GEval:
    """GEval metric for "plan_quality" or "helpfulness" with the 5-band rubric."""
    name, steps = METRICS[kind]
    return GEval(
        name=name,
        evaluation_steps=steps,
        evaluation_params=[Params.INPUT, Params.ACTUAL_OUTPUT],
        rubric=RUBRIC,
        model=judge,
        threshold=0.5,
        async_mode=False,
        verbose_mode=False,
    )


def _measure(kind: str, question: str, text: str, judge: DeepEvalBaseLLM) -> Dict[str, Any]:
    """Run one GEval metric (blocking) and return score10, band and reason."""
    metric = build_metric(kind, judge)
    case = LLMTestCase(input=question, actual_output=text)
    metric.measure(case, _show_indicator=False)
    score10 = float(metric.score) * 10.0
    return {
        "judge_score_0_10": round(score10, 2),
        "score": band_for(score10),
        "reason": (metric.reason or "").strip(),
    }


def score_text(
    kind: str,
    question: str,
    text: str,
    judge: DeepEvalBaseLLM,
    timeout: float = config.METRIC_TIMEOUT,
) -> Dict[str, Any]:
    """Score one text; never raises and never blocks longer than `timeout`.

    Result: {"score": 1-5 or None, "reason", "status", "error", "judge_score_0_10"}.
    status is "ok", "invalid_input", "timeout", "judge_error" or "bad_judge_output".
    """
    if not isinstance(question, str) or not question.strip() or not isinstance(text, str) or not text.strip():
        return {
            "score": None, "reason": "", "status": "invalid_input",
            "error": "question or text is empty or not a string", "judge_score_0_10": None,
        }
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_measure, kind, question, text, judge)
    try:
        out = future.result(timeout=timeout)
        return {**out, "status": "ok", "error": None}
    except FutureTimeout:
        return {"score": None, "reason": "", "status": "timeout",
                "error": f"metric did not finish within {timeout:.0f}s", "judge_score_0_10": None}
    except JudgeError as exc:
        return {"score": None, "reason": "", "status": "judge_error",
                "error": str(exc), "judge_score_0_10": None}
    except Exception as exc:  # DeepEval wraps judge errors; keep the message
        text_err = f"{type(exc).__name__}: {exc}"
        status = "judge_error" if "local judge call failed" in text_err else "bad_judge_output"
        return {"score": None, "reason": "", "status": status,
                "error": text_err[:400], "judge_score_0_10": None}
    finally:
        pool.shutdown(wait=False)


def plan_to_text(plan: List[str]) -> str:
    """Numbered plan, the text the Plan Quality metric reads."""
    return "\n".join(f"{i}. {step}" for i, step in enumerate(plan, 1))
