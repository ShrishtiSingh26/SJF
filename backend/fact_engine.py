"""Orchestrates PDF -> facts -> cross-document relationships, incrementally.

Uploading a new document only extracts facts from that document and compares its new
facts against facts already in the knowledge store - existing relationships are never
recomputed, so the store grows incrementally rather than rebuilding from scratch.
"""
import difflib
import logging
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from backend import llm, store
from backend.config import (
    CANDIDATE_MATCH_MIN_SIMILARITY,
    CANDIDATE_MATCH_TOP_K,
    COMPARISON_BATCH_SIZE,
    FUZZY_GROUND_MIN_RATIO,
)
from backend.pdf_extractor import chunk_pages, extract_pages

logger = logging.getLogger(__name__)


def _fact_text(fact: dict) -> str:
    return f"{fact.get('subject', '')}. {fact.get('statement', '')}"


def _normalize_whitespace(text: str) -> str:
    """Collapse all whitespace (including the tabs/newlines pdf_extractor.py uses to
    join table cells and rows) to single spaces, so a quote that is verbatim but was
    laid out differently in a table still passes the grounding check."""
    return re.sub(r"\s+", " ", text).strip()


def _quote_grounding(quote: str, chunk_text: str) -> tuple[bool, bool]:
    """Checks whether `quote` is grounded in `chunk_text`.

    Returns (verified, fuzzy): verified is True if the quote is either an exact
    substring (after whitespace normalization) or close enough via a fuzzy match to
    treat as grounded; fuzzy is True only in the second case, so callers can tell exact
    grounding apart from an approximate one for transparency.
    """
    norm_quote = _normalize_whitespace(quote)
    norm_text = _normalize_whitespace(chunk_text)
    if not norm_quote:
        return False, False
    if norm_quote in norm_text:
        return True, False
    matcher = difflib.SequenceMatcher(None, norm_quote, norm_text, autojunk=True)
    match = matcher.find_longest_match(0, len(norm_quote), 0, len(norm_text))
    ratio = match.size / len(norm_quote)
    return ratio >= FUZZY_GROUND_MIN_RATIO, True


def _apply_accounting_sign(item: dict) -> None:
    """Deterministically correct the standard accounting convention where a number in
    parentheses means negative (e.g. "(452 Cr)" = -452), instead of relying entirely on
    the LLM to have inferred that. Mutates item["value"] in place when the source quote
    shows the value's digits wrapped in parentheses and the model didn't already apply
    a negative sign."""
    value = item.get("value")
    quote = item.get("quote")
    if not isinstance(value, str) or not isinstance(quote, str) or value.startswith("-"):
        return
    value_digits = re.sub(r"[^\d.]", "", value)
    if not value_digits:
        return
    for paren_match in re.finditer(r"\(([^()]*\d[^()]*)\)", quote):
        paren_digits = re.sub(r"[^\d.]", "", paren_match.group(1))
        if paren_digits and paren_digits == value_digits:
            item["value"] = f"-{value}"
            return


def process_document(pdf_path: str, filename: str) -> dict:
    pages = extract_pages(pdf_path)
    if not any(p.text.strip() for p in pages):
        store.create_issue(None, None, "empty_document", f"No extractable text found in {filename}.")
        raise ValueError("No extractable text found in this PDF (it may be scanned/image-only).")

    document_id = store.create_document(filename=filename, page_count=len(pages))

    chunks = chunk_pages(pages)
    new_fact_ids: list[int] = []
    for chunk in chunks:
        try:
            extracted, truncated = llm.extract_facts(chunk.text)
        except Exception as exc:  # noqa: BLE001 - surfaced as a recorded extraction issue, not a crash
            logger.exception("Extraction failed for pages %s-%s", chunk.start_page, chunk.end_page)
            store.create_issue(
                document_id,
                chunk.start_page,
                "llm_extraction_error",
                f"LLM call failed for pages {chunk.start_page}-{chunk.end_page}: {exc}",
            )
            continue

        if truncated:
            store.create_issue(
                document_id,
                chunk.start_page,
                "truncated_extraction_response",
                f"Model's JSON response for pages {chunk.start_page}-{chunk.end_page} appeared cut off by "
                f"the output token limit; recovered {len(extracted)} complete facts from the partial response "
                "instead of discarding all of them.",
            )

        for item in extracted:
            page = item.get("page")
            if not isinstance(page, int) or not (chunk.start_page <= page <= chunk.end_page):
                store.create_issue(
                    document_id,
                    chunk.start_page,
                    "page_out_of_range",
                    f"Model reported page {page!r} outside chunk range {chunk.start_page}-{chunk.end_page}; "
                    f"defaulted to {chunk.start_page}.",
                    raw_excerpt=item.get("quote", ""),
                )
                item["page"] = chunk.start_page
            _apply_accounting_sign(item)
            verified, fuzzy = _quote_grounding(item.get("quote", ""), chunk.text)
            if not verified:
                store.create_issue(
                    document_id,
                    item.get("page"),
                    "ungrounded_quote",
                    "Model-provided quote was not found verbatim or close enough in the source chunk; "
                    "kept fact but flagged it as unverified.",
                    raw_excerpt=item.get("quote", ""),
                )
                item["verified_quote"] = False
            else:
                item["verified_quote"] = True
                if fuzzy:
                    item["verified_quote_fuzzy"] = True
            fact_id = store.create_fact(document_id, item)
            new_fact_ids.append(fact_id)

    relationships_found = _link_new_facts(document_id, new_fact_ids)

    return {
        "document_id": document_id,
        "filename": filename,
        "page_count": len(pages),
        "facts_extracted": len(new_fact_ids),
        "relationships_found": relationships_found,
    }


def _link_new_facts(document_id: int, new_fact_ids: list[int]) -> int:
    if not new_fact_ids:
        return 0

    all_facts = store.list_all_facts_with_doc()
    by_id = {f["id"]: f for f in all_facts}
    new_facts = [by_id[fid] for fid in new_fact_ids if fid in by_id]

    # Candidates are every other fact in the store, including other new facts from this
    # same document, so duplicate/related mentions within one filing (e.g. text vs. a
    # table) are also cross-checked - only the fact being compared against itself is excluded.
    candidate_pool = all_facts
    if not candidate_pool:
        return 0

    corpus = [_fact_text(f) for f in candidate_pool] + [_fact_text(f) for f in new_facts]
    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=4096)
        matrix = vectorizer.fit_transform(corpus)
    except ValueError:
        return 0

    pool_matrix = matrix[: len(candidate_pool)]
    new_matrix = matrix[len(candidate_pool) :]
    similarities = cosine_similarity(new_matrix, pool_matrix)

    # Gather every candidate pair up front so comparisons can be sent to the LLM in
    # batches, keeping API calls roughly linear in new-fact count rather than one
    # request per pair (important on a rate-limited free tier).
    candidate_pairs: list[tuple[dict, dict]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for i, new_fact in enumerate(new_facts):
        sims = similarities[i]
        ranked = sorted(range(len(candidate_pool)), key=lambda idx: sims[idx], reverse=True)
        checked = 0
        for idx in ranked:
            if checked >= CANDIDATE_MATCH_TOP_K:
                break
            if sims[idx] < CANDIDATE_MATCH_MIN_SIMILARITY:
                break
            candidate = candidate_pool[idx]
            if candidate["id"] == new_fact["id"]:
                continue
            if store.relationship_exists(new_fact["id"], candidate["id"]):
                continue
            pair_key = tuple(sorted((new_fact["id"], candidate["id"])))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            candidate_pairs.append((new_fact, candidate))
            checked += 1

    relationships_found = 0
    for start in range(0, len(candidate_pairs), COMPARISON_BATCH_SIZE):
        batch = candidate_pairs[start : start + COMPARISON_BATCH_SIZE]
        try:
            results = llm.compare_facts_batch(batch)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Batch comparison failed for %d pairs", len(batch))
            store.create_issue(
                document_id,
                None,
                "llm_comparison_error",
                f"Batch comparison of {len(batch)} fact pairs failed: {exc}",
            )
            continue
        for (fact_a, fact_b), result in zip(batch, results):
            relation_type = result.get("relation_type", "unrelated")
            if relation_type == "unrelated":
                continue
            raw_confidence = result.get("confidence")
            store.create_relationship(
                fact_a["id"],
                fact_b["id"],
                relation_type,
                result.get("explanation", ""),
                float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.5,
            )
            relationships_found += 1
    return relationships_found
