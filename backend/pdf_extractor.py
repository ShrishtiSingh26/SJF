"""Layout-aware text extraction from PDFs, grouped into chunks for the LLM."""
from dataclasses import dataclass

import pdfplumber

from backend.config import CHUNK_PAGE_SIZE


@dataclass
class PageText:
    page_number: int  # 1-indexed
    text: str


@dataclass
class Chunk:
    start_page: int
    end_page: int
    text: str


def extract_pages(pdf_path: str) -> list[PageText]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            tables = page.extract_tables()
            table_text = ""
            for t_idx, table in enumerate(tables):
                rows = ["\t".join(cell or "" for cell in row) for row in table if row]
                if rows:
                    table_text += f"\n[Table {t_idx + 1} on page {i}]\n" + "\n".join(rows)
            pages.append(PageText(page_number=i, text=(text + table_text).strip()))
    return pages


def chunk_pages(pages: list[PageText], pages_per_chunk: int = CHUNK_PAGE_SIZE) -> list[Chunk]:
    chunks = []
    for i in range(0, len(pages), pages_per_chunk):
        group = pages[i : i + pages_per_chunk]
        if not any(p.text.strip() for p in group):
            continue
        labeled = "\n\n".join(f"--- Page {p.page_number} ---\n{p.text}" for p in group)
        chunks.append(Chunk(start_page=group[0].page_number, end_page=group[-1].page_number, text=labeled))
    return chunks
