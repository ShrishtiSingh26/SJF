import json

from backend.db import get_cursor, row_to_dict


def create_document(filename: str, page_count: int) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO documents (filename, page_count) VALUES (?, ?)",
            (filename, page_count),
        )
        return cur.lastrowid


def list_documents() -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM documents ORDER BY id DESC")
        return [row_to_dict(r) for r in cur.fetchall()]


def get_document(document_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        row = cur.fetchone()
        return row_to_dict(row) if row else None


def create_fact(document_id: int, fact: dict) -> int:
    metadata = {
        k: v
        for k, v in fact.items()
        if k not in {"page", "category", "subject", "statement", "value", "unit", "period", "quote", "confidence"}
    }
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO facts
               (document_id, page, category, subject, statement, value, unit, period, quote, confidence, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                document_id,
                fact.get("page", 0),
                fact.get("category", "uncategorized"),
                fact.get("subject", ""),
                fact.get("statement", ""),
                str(fact.get("value")) if fact.get("value") is not None else None,
                fact.get("unit"),
                fact.get("period"),
                fact.get("quote", ""),
                float(fact["confidence"]) if isinstance(fact.get("confidence"), (int, float)) else 0.5,
                json.dumps(metadata),
            ),
        )
        return cur.lastrowid


def get_fact(fact_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute(
            """SELECT facts.*, documents.filename AS document_filename
               FROM facts JOIN documents ON documents.id = facts.document_id
               WHERE facts.id = ?""",
            (fact_id,),
        )
        row = cur.fetchone()
        return row_to_dict(row) if row else None


def list_facts(document_id: int | None = None, category: str | None = None, q: str | None = None) -> list[dict]:
    query = """SELECT facts.*, documents.filename AS document_filename
               FROM facts JOIN documents ON documents.id = facts.document_id WHERE 1=1"""
    params: list = []
    if document_id is not None:
        query += " AND facts.document_id = ?"
        params.append(document_id)
    if category:
        query += " AND facts.category = ?"
        params.append(category)
    if q:
        query += " AND (facts.statement LIKE ? OR facts.subject LIKE ? OR facts.quote LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    query += " ORDER BY facts.id DESC"
    with get_cursor() as cur:
        cur.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]


def list_all_facts_with_doc() -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT facts.*, documents.filename AS document_filename
               FROM facts JOIN documents ON documents.id = facts.document_id"""
        )
        return [row_to_dict(r) for r in cur.fetchall()]


def list_categories() -> list[str]:
    with get_cursor() as cur:
        cur.execute("SELECT DISTINCT category FROM facts ORDER BY category")
        return [r["category"] for r in cur.fetchall()]


def create_relationship(fact_id_a: int, fact_id_b: int, relation_type: str, explanation: str, confidence: float) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO relationships (fact_id_a, fact_id_b, relation_type, explanation, confidence)
               VALUES (?, ?, ?, ?, ?)""",
            (fact_id_a, fact_id_b, relation_type, explanation, confidence),
        )
        return cur.lastrowid


def list_relationships(relation_type: str | None = None) -> list[dict]:
    query = "SELECT * FROM relationships WHERE 1=1"
    params: list = []
    if relation_type:
        query += " AND relation_type = ?"
        params.append(relation_type)
    query += " ORDER BY id DESC"
    with get_cursor() as cur:
        cur.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]


def relationship_exists(fact_id_a: int, fact_id_b: int) -> bool:
    with get_cursor() as cur:
        cur.execute(
            """SELECT 1 FROM relationships
               WHERE (fact_id_a = ? AND fact_id_b = ?) OR (fact_id_a = ? AND fact_id_b = ?)""",
            (fact_id_a, fact_id_b, fact_id_b, fact_id_a),
        )
        return cur.fetchone() is not None


def create_issue(document_id: int | None, page: int | None, issue_type: str, description: str, raw_excerpt: str = ""):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO extraction_issues (document_id, page, issue_type, description, raw_excerpt)
               VALUES (?, ?, ?, ?, ?)""",
            (document_id, page, issue_type, description, raw_excerpt),
        )
        return cur.lastrowid


def list_issues() -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM extraction_issues ORDER BY id DESC")
        return [row_to_dict(r) for r in cur.fetchall()]
