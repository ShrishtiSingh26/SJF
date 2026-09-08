import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import fact_engine, llm, store
from backend.config import BASE_DIR, UPLOAD_DIR
from backend.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Fact Knowledge Layer", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = fact_engine.process_document(str(dest), file.filename)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result


@app.get("/api/documents")
def get_documents():
    return store.list_documents()


@app.get("/api/facts")
def get_facts(document_id: int | None = None, category: str | None = None, q: str | None = None):
    return store.list_facts(document_id=document_id, category=category, q=q)


@app.get("/api/facts/{fact_id}")
def get_fact(fact_id: int):
    fact = store.get_fact(fact_id)
    if not fact:
        raise HTTPException(404, "Fact not found")
    relationships = [
        r for r in store.list_relationships() if r["fact_id_a"] == fact_id or r["fact_id_b"] == fact_id
    ]
    enriched = []
    for r in relationships:
        other_id = r["fact_id_b"] if r["fact_id_a"] == fact_id else r["fact_id_a"]
        other = store.get_fact(other_id)
        enriched.append({**r, "other_fact": other})
    return {**fact, "relationships": enriched}


@app.get("/api/categories")
def get_categories():
    return store.list_categories()


@app.get("/api/relationships")
def get_relationships(relation_type: str | None = None):
    relationships = store.list_relationships(relation_type=relation_type)
    enriched = []
    for r in relationships:
        enriched.append(
            {
                **r,
                "fact_a": store.get_fact(r["fact_id_a"]),
                "fact_b": store.get_fact(r["fact_id_b"]),
            }
        )
    return enriched


@app.get("/api/issues")
def get_issues():
    return store.list_issues()


@app.get("/api/cases")
def get_showcase_cases():
    """Auto-selects the strongest example of each required case from stored data.

    Nothing here is hard-coded to specific facts/filenames: it picks the
    highest-confidence relationship of each type currently in the knowledge store.
    """

    def best(relation_type: str):
        candidates = store.list_relationships(relation_type=relation_type)
        if not candidates:
            return None
        enriched = [
            {**r, "fact_a": store.get_fact(r["fact_id_a"]), "fact_b": store.get_fact(r["fact_id_b"])}
            for r in candidates
        ]
        # Prefer cross-document examples as a tiebreak: a relationship spanning two
        # different source documents is a stronger, more literal demonstration of
        # "across documents" than one that happens to tie on confidence within a
        # single document.
        def sort_key(r):
            cross_document = r["fact_a"]["document_id"] != r["fact_b"]["document_id"]
            return (r["confidence"], cross_document)

        return max(enriched, key=sort_key)

    return {
        "corroborated": best("corroborates"),
        "contradiction": best("contradicts"),
        "reconciled": best("reconciled"),
        "extraction_or_reasoning_failures": store.list_issues()[:10],
    }


@app.get("/api/query")
def query_facts(q: str):
    facts = store.list_facts(q=q)[:15]
    if not facts:
        # Fall back to a broader set so the model can still try to help.
        facts = store.list_all_facts_with_doc()[:40]
    if not facts:
        return {"answer": "No facts in the knowledge store yet. Upload a PDF first.", "facts_used": []}
    try:
        answer = llm.answer_query(q, facts)
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean error, not a raw 500
        raise HTTPException(502, f"Query failed: {exc}") from exc
    return {"answer": answer, "facts_used": [f["id"] for f in facts]}


frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
