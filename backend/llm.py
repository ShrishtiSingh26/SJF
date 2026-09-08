"""Thin wrapper around the Gemini API for fact extraction and cross-document reasoning.

No fact schema, category list, or document-specific rule is hard-coded here: the model
decides what counts as a fact and what category it belongs to for each document it sees.
"""
import json
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from backend.config import GEMINI_API_KEY, LLM_MODEL

_client = None

_RETRYABLE_CODES = {429, 503}
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 2.0


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env.")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _is_daily_quota_exhausted(exc: genai_errors.ClientError) -> bool:
    """A per-day quota (as opposed to a per-minute rate limit) will not recover within
    this process's lifetime, so retrying it is pure wasted time - fail fast instead."""
    message = str(exc)
    return "PerDay" in message or "generate_content_free_tier_requests" in message


def _generate(system_prompt: str, user_content: str, max_output_tokens: int, as_json: bool = True) -> str:
    client = get_client()
    # Low, near-deterministic temperature: this is a structured extraction/classification
    # task, not creative generation, and a high default temperature was observed to make
    # the model read different numbers off the same source table across identical runs -
    # undermining both grounding accuracy and result reproducibility.
    config_kwargs = {"system_instruction": system_prompt, "max_output_tokens": max_output_tokens, "temperature": 0.1}
    if as_json:
        config_kwargs["response_mime_type"] = "application/json"
    last_error = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=LLM_MODEL,
                contents=user_content,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            return resp.text or ""
        except genai_errors.ClientError as exc:
            last_error = exc
            if getattr(exc, "code", None) not in _RETRYABLE_CODES or attempt == _MAX_RETRIES:
                raise
            if getattr(exc, "code", None) == 429 and _is_daily_quota_exhausted(exc):
                raise
            time.sleep(_BASE_BACKOFF_SECONDS * (2**attempt))
        except genai_errors.ServerError as exc:
            last_error = exc
            if attempt == _MAX_RETRIES:
                raise
            time.sleep(_BASE_BACKOFF_SECONDS * (2**attempt))
    raise last_error  # pragma: no cover - unreachable, satisfies type checkers


def _extract_json(text: str):
    """Pull the first top-level JSON array/object out of a model response."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    text = text.strip()
    start_chars = "[{"
    start = next((i for i, c in enumerate(text) if c in start_chars), None)
    if start is None:
        raise ValueError("No JSON found in model response")
    opener = text[start]
    closer = "]" if opener == "[" else "}"
    depth = 0
    for i in range(start, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("Unbalanced JSON in model response")


def _extract_json_array_partial(text: str) -> list:
    """Best-effort recovery when a JSON array response was cut off mid-array by an
    output-token limit: parses as many complete top-level {...} objects as it can find
    in sequence, and stops cleanly at the first one that isn't complete (the truncated
    tail) instead of discarding every fact the response did contain."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    text = text.strip()
    start = text.find("[")
    if start == -1:
        return []
    objects: list = []
    i = start + 1
    n = len(text)
    while i < n:
        while i < n and text[i] not in "{]":
            i += 1
        if i >= n or text[i] == "]":
            break
        depth = 0
        in_string = False
        escape = False
        j = i
        obj_end = None
        while j < n:
            ch = text[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    obj_end = j
                    break
            j += 1
        if obj_end is None:
            break  # object cut off mid-way by the token limit; stop, don't guess
        try:
            objects.append(json.loads(text[i : obj_end + 1]))
        except json.JSONDecodeError:
            break
        i = obj_end + 1
    return objects


EXTRACTION_SYSTEM_PROMPT = """You are a meticulous financial and business document analyst building a \
fact knowledge layer. You read a chunk of a real-world document and extract discrete, checkable facts.

A "fact" is a specific, checkable claim: a number, a date, a status, a relationship, or a named \
attribute of an entity. Prefer facts that could be corroborated or contradicted by another document \
(financial figures, operational metrics, dates, people/roles, macro statistics, addresses, etc.). \
Do not invent a fixed taxonomy - choose whatever "category" label best describes each fact you find \
(e.g. "revenue", "headcount", "director_status", "inflation_rate", "address" - or something else \
entirely if that fits better). Skip boilerplate, table of contents, and filler text.

For every fact, you MUST quote the exact supporting text verbatim from the given chunk (the "quote" \
field), and you MUST report which page it came from using the page markers in the text \
(e.g. "--- Page 12 ---" means content until the next marker is on page 12).

The "quote" MUST be a single contiguous span copied character-for-character from the chunk - never \
synthesize it by joining multiple cells, rows, or columns from a table into one string (e.g. do not \
merge a current-year and a prior-year figure from the same table row into one quote). If a table row \
has a metric for several periods (e.g. FY24 and FY23 side by side), extract ONE fact per period, each \
quoting only that period's own cell/line, rather than one fact whose quote spans several columns.

Return ONLY a JSON array, no prose, where each element has this shape:
{
  "page": <integer page number from the page markers>,
  "category": "<short snake_case label you choose>",
  "subject": "<the entity/metric the fact is about, e.g. 'Delhivery consolidated revenue' or 'India CPI inflation'>",
  "statement": "<a clear one-sentence paraphrase of the fact>",
  "value": "<the number/status/name if applicable, else null>",
  "unit": "<unit of the value if applicable (INR crore, %, count, date, etc.), else null>",
  "period": "<the time period/fiscal year/as-of date the fact applies to, else null>",
  "quote": "<verbatim supporting quote from the chunk, kept short but complete>",
  "confidence": <float 0-1, your confidence this is accurately extracted>
}

If the chunk has no extractable facts, return an empty JSON array [].
Extract at most 60 of the most important, checkable facts from this chunk, spread across its
different sections rather than concentrated in one part - prioritize quality and coverage over volume.
"""


class ExtractionParseError(Exception):
    """Raised when a model response for fact extraction couldn't be parsed as JSON at
    all (not even partially) - this is a genuine failure to surface, not a silent []."""


def extract_facts(chunk_text: str) -> tuple[list[dict], bool]:
    """Returns (facts, truncated). truncated is True when the response looked like it
    was cut off by the output-token limit and facts were recovered from the partial
    array rather than a clean parse - callers should log this rather than treat it as
    an ordinary result."""
    raw = _generate(EXTRACTION_SYSTEM_PROMPT, chunk_text, max_output_tokens=8192)
    truncated = False
    try:
        data = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        data = _extract_json_array_partial(raw)
        if not data:
            raise ExtractionParseError(
                f"Model response could not be parsed as JSON, even partially (response length {len(raw)} chars)."
            )
        truncated = True
    if not isinstance(data, list):
        raise ExtractionParseError("Model response was valid JSON but not the expected array shape.")
    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not item.get("quote") or not item.get("statement"):
            continue
        cleaned.append(item)
    return cleaned, truncated


BATCH_COMPARISON_SYSTEM_PROMPT = """You compare pairs of facts extracted from documents to decide how \
each pair relates. You are given a JSON array of pairs; each pair has fact "a" and fact "b" with their \
statement, value, unit, period, subject, and verbatim source quote for grounding. Do not assume two \
facts are related just because they look similar - check the subject, scope, period, and units carefully.

For EACH pair, classify the relationship as exactly one of:
- "corroborates": both facts assert the same underlying truth, even if worded, scoped, or rounded differently.
- "contradicts": the facts assert incompatible claims about the same subject/scope/period that cannot both be true.
- "reconciled": the facts look contradictory at first glance but are both true because of a difference in \
time period, scope, unit, or definition - explain exactly what reconciles them.
- "unrelated": the facts are not meaningfully comparable (different subjects, coincidental overlap, etc.).

Return ONLY a JSON array with exactly one result per input pair, IN THE SAME ORDER, each shaped:
{
  "pair_index": <the integer index of this pair in the input array>,
  "relation_type": "corroborates" | "contradicts" | "reconciled" | "unrelated",
  "explanation": "<2-3 sentences citing the specific numbers/periods/scopes from both quotes that justify your classification>",
  "confidence": <float 0-1>
}
"""


def _fact_payload(fact: dict) -> dict:
    return {
        "document": fact.get("document_filename"),
        "subject": fact.get("subject"),
        "statement": fact.get("statement"),
        "value": fact.get("value"),
        "unit": fact.get("unit"),
        "period": fact.get("period"),
        "quote": fact.get("quote"),
    }


def compare_facts_batch(pairs: list[tuple[dict, dict]]) -> list[dict]:
    """Classify many fact pairs in a single LLM call to keep API usage roughly linear in
    the number of new facts rather than requiring one call per candidate pair."""
    if not pairs:
        return []
    payload = [{"a": _fact_payload(a), "b": _fact_payload(b)} for a, b in pairs]
    raw = _generate(BATCH_COMPARISON_SYSTEM_PROMPT, json.dumps(payload, indent=2), max_output_tokens=4096)
    fallback = [{"relation_type": "unrelated", "explanation": "Could not parse batch comparison result.", "confidence": 0.0} for _ in pairs]
    try:
        data = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return fallback
    if not isinstance(data, list):
        return fallback
    results = list(fallback)
    for item in data:
        if not isinstance(item, dict):
            continue
        idx = item.get("pair_index")
        if not isinstance(idx, int) or not (0 <= idx < len(pairs)):
            continue
        if "relation_type" not in item:
            continue
        results[idx] = item
    return results


QUERY_SYSTEM_PROMPT = """You answer questions using ONLY the provided facts (each with its source \
document, page, and verbatim quote). Cite the specific facts you used by their id in square brackets, \
e.g. "[fact 12]". If the facts don't contain enough information to answer, say so plainly instead of \
guessing. Be concise."""


def answer_query(question: str, facts: list[dict]) -> str:
    facts_text = "\n\n".join(
        f"[fact {f['id']}] ({f['document_filename']}, p.{f['page']}) {f['statement']} "
        f"(value={f.get('value')}, unit={f.get('unit')}, period={f.get('period')}) "
        f"Quote: \"{f['quote']}\""
        for f in facts
    )
    return _generate(QUERY_SYSTEM_PROMPT, f"Facts:\n{facts_text}\n\nQuestion: {question}", max_output_tokens=1024, as_json=False)
