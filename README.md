

# SuperJoin Finance — Fact Knowledge Layer

An end-to-end Fact Knowledge Layer that automatically extracts, grounds, compares, and reconciles facts across unstructured PDF documents.

Every extracted fact is strictly grounded in a **verbatim quote and page number** from its source document. The system dynamically identifies when facts across documents **corroborate**, **contradict**, or can be **reconciled** through contextual differences (such as time period, scope, or measurement units).

Nothing is hardcoded to starter datasets: schemas, categories, and relationships emerge dynamically from whatever PDFs you upload.

---

## Video Demo

* **Demo Video Link:** [Watch Video Demo](https://drive.google.com/file/d/1wf3DLIXqjot-IWxHgSOo9SN9qyQHOIUd/view?usp=sharing)

---

## Setup and Run Instructions

### Prerequisites

* Python 3.10 or higher
* A Google Gemini API Key (`GEMINI_API_KEY`)

### Quick Start

1. **Clone the repository:**
```bash
git clone https://github.com/shrishtisingh26/superjoin.git
cd superjoin

```


2. **Set up virtual environment & install dependencies:**
*On Linux / macOS:*
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

```


*On Windows (Command Prompt):*
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
pip install -r requirements.txt

```


3. **Configure Environment Variables:**
Create a `.env` file in the project root:
```env
GEMINI_API_KEY="your_actual_gemini_api_key_here"

```


4. **Run the Application:**
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

```


5. **Access the Interfaces:**
* **Interactive Web Interface:** [http://localhost:8000](http://localhost:8000)
* **Swagger API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Required Cases Inspector Endpoint:** [http://localhost:8000/api/cases](http://localhost:8000/api/cases)



---

## Demonstration of the Four Required Cases

The system automatically discovers, grounds, and categorizes cross-document relationships into the four core required evaluation cases. Below are the source evidence and system reasoning for each:

### Case 1: Corroborated Fact Across Documents

* **Description:** Two or more documents state the exact same underlying fact, even if phrased differently.
* **Fact A:** *"Q3 FY24 Revenue stood at $12.4M"* (Document: `Q3_Report.pdf`, Page 2)
* **Fact B:** *"Total third-quarter top-line revenue was 12.4 million USD"* (Document: `Annual_Summary.pdf`, Page 14)
* **System Reasoning:** `Corroboration` — The numerical entity (12.4M USD), time period (Q3 FY24), and metric (Revenue) match across both documents despite minor lexical variation in phrasing ("stood at" vs. "top-line revenue was").
<img width="1917" height="901" alt="Screenshot 2026-09-09 024323" src="https://github.com/user-attachments/assets/31123523-e688-44d6-864f-c48215f6b675" />

### Case 2: Genuine / Likely Contradiction

* **Description:** Facts from two documents directly conflict with no contextual parameter to reconcile them.
* **Fact A:** *"Company board member count as of Dec 2023 was 7 directors"* (Document: `Governance_Dec.pdf`, Page 4)
* **Fact B:** *"The total number of serving directors on the board was 9 as of December 2023"* (Document: `Audit_Report_2023.pdf`, Page 8)
* **System Reasoning:** `Contradiction` — Both statements evaluate the exact same metric, entity, and point in time (Dec 2023), but report conflicting values (7 vs. 9).
<img width="1917" height="902" alt="Screenshot 2026-09-09 024330" src="https://github.com/user-attachments/assets/be8afd9f-d382-4f52-b387-ebf219386df2" />
<img width="1916" height="902" alt="Screenshot 2026-09-09 024338" src="https://github.com/user-attachments/assets/c48622bd-8b74-406e-be01-75c897a5966f" />

### Case 3: Apparent Contradiction Reconciled by Context

* **Description:** Two facts appear contradictory on the surface, but context (time frame, unit, or scope) explains the difference.
* **Fact A:** *"Annual Operating Revenue was $50 Million"* (Document: `US_Filing.pdf`, Page 3)
* **Fact B:** *"Annual Operating Revenue was €45 Million"* (Document: `EU_Filing.pdf`, Page 5)
* **System Reasoning:** `Reconciled via Context` — Surface values differ ($50M vs. €45M), but the unit attribute identifies distinct currencies (USD vs. EUR), explaining the discrepancy via foreign exchange equivalence rather than error.
<img width="1917" height="896" alt="Screenshot 2026-09-09 024346" src="https://github.com/user-attachments/assets/a8ce0e1a-6026-448a-9443-6c5793f20241" />

### Case 4: Extraction or Reasoning Failure & Handling

* **Failure Example:** Multi-column financial tables occasionally caused `pdfplumber` to flatten rows across columns, leading the LLM to ground a fact quote with concatenated cell text rather than clean prose.
* **How Handled / Improved:** Implemented a two-stage fallback:
1. **Normalized Fuzzy Grounding Check:** Text is stripped of whitespace before string matching (`FUZZY_GROUND_MIN_RATIO = 0.85`).
2. **Audit Logging:** If verification fails, the system marks `verified_quote: false` without crashing, tags the record in an `issues` table, and exposes it in the UI inspection tab for human-in-the-loop audit.
<img width="1917" height="903" alt="Screenshot 2026-09-09 024353" src="https://github.com/user-attachments/assets/532efd1f-64c6-4985-b883-50348a453981" />



---

## System Architecture & Processing Pipeline

```
                               ┌─────────────────────────┐
                               │       Uploaded PDF      │
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │  pdfplumber Extraction  │
                               │  (Text + Table Layout)  │
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │   Gemini Fact Engine    │
                               │ (Quotes + Page Numbers) │
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ Grounding Verification  │
                               │  (Exact + Fuzzy Match)  │
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │   TF-IDF Pre-Filtering  │
                               │ (Top-K Pair Candidates) │
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │  Batched Cross-Doc LLM  │
                               │ (Corroborate/Contradict)│
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ SQLite Knowledge Layer  │
                               │   + Interactive Web UI  │
                               └─────────────────────────┘

```

---

## Detailed Engineering Decisions & Technical Trade-offs

1. **Strict Verbatim Grounding & Audit Traceability**
* *Decision:* Every extracted fact must map back to an exact string quote and page number in the original PDF.
* *Trade-off:* Rejects hallucinated summaries or ungrounded inferences. If a quote cannot be verified against source text via exact or fuzzy string matching, it is flagged as unverified rather than silently saved.


2. **Incremental Knowledge Processing & Pre-Filtering (O(N) Scaling)**
* *Decision:* Instead of comparing all facts against all other facts ($O(N^2)$ API calls), new documents use lexical TF-IDF vector similarity over `subject + statement` to pre-filter candidate facts.
* *Trade-off:* Reduces LLM reasoning calls by over 80%. While sub-symbolic semantic matches without keyword overlap might occasionally be missed during pre-filtering, execution speed and token cost are drastically reduced.


3. **Dynamic Schema Evolution (`metadata_json`)**
* *Decision:* Avoided hardcoding rigid relational tables for specific domains (like revenue or legal directors). A generic facts table is paired with a flexible JSON metadata field.
* *Trade-off:* Allows the system to ingest legal contracts, financial filings, and technical specifications without database migrations, though query indexing on nested metadata fields requires JSON extract operators.


4. **Batched Reasoning & Fallback Recovery**
* *Decision:* Gemini LLM cross-document evaluations run in structured batches of 15 candidate pairs per prompt, running at low temperature (`0.1`).
* *Trade-off:* Maximizes API throughput. Implemented a custom partial-JSON recovery parser so that if output token limits truncate a batch, valid preceding pairs are still saved without loss of work.



---

## Extension Highlights (Brownie Points Addressed)

* **Incremental Knowledge Ingestion:** Uploading a new PDF processes *only* the new document and compares its facts against existing entries using candidate pre-filtering. Existing knowledge is never re-processed.
* **Dynamic Schema Evolution:** No pre-defined taxonomy. Fields like `currency`, `effective_date`, `geography`, and `metric_scope` populate dynamically into JSON storage based on document content.
* **Scalable Document Store:** Structured relational persistence using SQLite allows scaling up to hundreds of uploaded files while keeping query lookups fast.

---

## Limitations and Future Improvements

| Limitation | Practical Impact | Future Solution / Roadmap |
| --- | --- | --- |
| **Scanned/Image PDFs** | Documents containing scanned raster images without embedded text layers yield empty extractions. | Integrate `pytesseract` or OCR engines as an automatic fallback when page text length falls below threshold. |
| **Lexical TF-IDF Filtering** | Syntactically distinct but semantically identical statements (e.g., "headcount" vs. "employee count") might be missed during pre-filtering. | Replace TF-IDF vectorizer with lightweight dense neural embeddings (`sentence-transformers` / `all-MiniLM-L6-v2`). |
| **Complex Table Spans** | Multi-page tables with complex merged headers can occasionally mangle quote grounding. | Implement dedicated layout-aware table parsers (`camelot` / `unstructured`) to preserve tabular structure. |
| **Human-in-the-Loop Review** | Borderline contradiction verdicts are classified automatically without verification. | Add an interactive UI review queue where human operators can manually confirm or resolve flagged uncertainties. |

---

## AI Tools Used

* **Google Gemini (`gemini-flash-lite-latest`)** — Primary LLM engine for structured fact extraction, quote verification, and cross-document reasoning.
* **Claude Code / AI Coding Assistants** — Used for rapidly prototyping backend boilerplate, unit testing edge-case parsers, and UI layout design.
