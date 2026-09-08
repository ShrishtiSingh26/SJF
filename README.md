<div align="center">

# SuperJoin Finance


[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Gemini-flash--lite-4285F4?logo=googlegemini&logoColor=white)](https://ai.google.dev/)

</div>

---

Every extracted fact is strictly grounded in a **verbatim quote and page number** from its source document nothing is trusted blindly. The system automatically discovers when facts across documents **corroborate**, **contradict**, or can be **reconciled** through context (such as time period, scope, or units).

Nothing is hard-coded to starter datasets: the schema, categories, and relationships all emerge dynamically from whatever PDFs you upload.

<div align="center">
<a href="....">
  <img src="..." width="720" alt="Demo video" />
  <br/>
  
</a>
</div>

---

## Setup and Run Instructions

### Prerequisites
- Python 3.10+
-FastAPI
- Google Gemini API Key 
### Quick Start

**Clone the repository**
```bash
git clone https://github.com/shrishtisingh26/superjoin.git
cd superjoin
```
**Access the application**

*Windows (Command Prompt):*
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```


- Web Interface: [http://localhost:8000](http://localhost:8000)
- API Documentation (Swagger UI): [http://localhost:8000/docs](http://localhost:8000/docs)


---

## The Four Required Cases (Screenshots)


---

## Approach & Architecture

```
                               ┌─────────────────────────┐
                               │       Uploaded PDF       │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │  pdfplumber Extraction   │
                               │  (Text + Table Layout)   │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │   Gemini Fact Engine     │
                               │ (Quotes + Page Numbers)  │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ Grounding Verification   │
                               │ (Exact + Fuzzy Match)    │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │  TF-IDF Pre-Filtering    │
                               │ (Top-K Pair Candidates)  │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │  Batched Cross-Doc LLM   │
                               │ (Corroborate/Contradict) │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ SQLite Knowledge Layer   │
                               │ + Interactive Web UI     │
                               └─────────────────────────┘
```

### Engineering Decisions & Key Technical Approaches

**1. Strict Grounding & Verification**
Every extracted fact must provide a verbatim quote and page number. Text is normalized for whitespace to handle `pdfplumber` cell joins. If an exact match fails, a fuzzy overlap check (`FUZZY_GROUND_MIN_RATIO = 0.85` in `backend/config.py`) handles minor formatting drift. Failing quotes are flagged `verified_quote: false` and recorded in the issue log.

**2. Incremental Knowledge Updates & Candidate Pre-Filtering**
Uploading a new PDF does not re-process existing documents or recompute previous relationships. Newly extracted facts are vectorized using TF-IDF over `subject + statement` text to locate the top-K most relevant facts in the store across all documents. Candidate pairs are classified in batches (15 pairs per LLM call) into `corroborates`, `contradicts`, `reconciled`, or `unrelated`. Batched calls dramatically reduce API request overhead.

**3. Dynamic Schema Evolution**
No hardcoded categories or fixed attributes. SQLite stores standard columns (`subject`, `statement`, `value`, `unit`, `period`, `quote`, `page`, `confidence`) alongside a flexible `metadata_json` blob for domain-specific attributes discovered on the fly.

**4. Low Temperature & Token Safety**
LLM calls run at `temperature = 0.1` to ensure consistent numerical extraction across identical runs. Includes a fallback JSON recovery mechanism that parses complete JSON array items even if the LLM output is truncated by token limits.

### AI Tools Used
- **Google Gemini (`gemini-flash-lite-latest`)** — Primary extraction, grounding validation, and cross-document reasoning engine (chosen for high speed, large context window, and generous free tier).
- **Claude Code & Antigravity AI** — Coding assistant used during development, debugging, unit testing, and documentation writing.

---

## How This Addresses the "Brownie Points"

- **Large PDFs without performance issues** — Single-pass whole-document chunking fits 100+ page filings into Gemini's 1M+ token context window, avoiding dozens of micro-calls.
- **Incremental updates** — Only new facts are compared against existing candidates using TF-IDF candidate selection.
- **Dynamic schema evolution** — Categories and attributes emerge naturally from document content and are saved in `metadata_json`.
- **Scalable multi-document store** — Persists documents, facts, relationships, and issues cleanly in SQLite.

---

## Trade-offs, Limitations & Next Steps

| Limitation | Impact | Planned Next Step / Fix |
| :--- | :--- | :--- |
| **Scanned / Image PDFs** | `pdfplumber` cannot extract text from scanned images. | Integrate Tesseract OCR as a fallback for non-text PDF pages. |
| **TF-IDF vs. Vector Embeddings** | Lexical TF-IDF might miss semantically identical facts with completely different wording. | Replace TF-IDF with lightweight dense embeddings (`sentence-transformers`). |
| **Table vs. Prose Provenance** | Fact quotes from complex tables can occasionally misalign column headers. | Add explicit table structure parsing to tag table provenance on extracted facts. |
| **Human-in-the-Loop Queue** | Low-confidence relationship verdicts are accepted automatically. | Build an interactive moderation queue for relationships with confidence < 0.5. |

---

## Additional Notes

- The system runs entirely locally using SQLite and Python.
- All four required cases are dynamically retrieved via `GET /api/cases` from whatever facts are stored in the database.
- Thanks for reviewing this assignment — I had a great time building it.