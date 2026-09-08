import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-flash-lite-latest")

DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "knowledge.sqlite3"))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Number of PDF pages grouped into a single extraction chunk sent to the LLM. Gemini's
# large context window lets most documents fit in one chunk, which keeps API usage (and
# free-tier quota consumption) roughly constant per document instead of scaling with page count.
CHUNK_PAGE_SIZE = int(os.environ.get("CHUNK_PAGE_SIZE", "120"))

# How many top-similar existing facts to compare a new fact against.
CANDIDATE_MATCH_TOP_K = int(os.environ.get("CANDIDATE_MATCH_TOP_K", "3"))
CANDIDATE_MATCH_MIN_SIMILARITY = float(os.environ.get("CANDIDATE_MATCH_MIN_SIMILARITY", "0.18"))

# How many candidate fact pairs are sent to the LLM per batched comparison call.
COMPARISON_BATCH_SIZE = int(os.environ.get("COMPARISON_BATCH_SIZE", "15"))

# A quote that isn't an exact substring of its source chunk is still accepted as grounded
# if its longest contiguous match against the chunk covers at least this fraction of the
# quote's length (handles minor paraphrasing/whitespace drift without trusting free-form
# rewrites). Below this, the fact is kept but flagged verified_quote: false.
FUZZY_GROUND_MIN_RATIO = float(os.environ.get("FUZZY_GROUND_MIN_RATIO", "0.85"))
