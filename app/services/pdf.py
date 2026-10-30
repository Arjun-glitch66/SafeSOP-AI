"""Reading the immutable original PDF and rendering drafts as PDF."""
import html
import io
import logging
import os
import shutil
from functools import lru_cache

import pymupdf
from fastapi import HTTPException

from app import config

logger = logging.getLogger("safesop")


# ---- OCR fallback for scanned pages (PyMuPDF's built-in Tesseract integration) ----

def ocr_available():
    return bool(shutil.which("tesseract") or os.getenv("TESSDATA_PREFIX"))


@lru_cache(maxsize=256)
def _ocr_text(path, page_index, modified):
    """OCR one page. Cached per file version: OCR takes seconds a page and the same text is read
    for generation, comparison and re-checks. ponytail: in-process cache; persist it if it matters."""
    with pymupdf.open(path) as pdf:
        page = pdf[page_index]
        textpage = page.get_textpage_ocr(language=config.OCR_LANGUAGES, dpi=300, full=True)
        return page.get_text(sort=True, textpage=textpage).strip()


def page_text(page, path):
    """The page's own text, or its OCR text when it has (almost) none and OCR is installed."""
    text = page.get_text(sort=True).strip()
    if len(text) >= config.OCR_MIN_CHARS or not ocr_available():
        return text
    return _ocr_text(str(path), page.number, os.path.getmtime(path))


def pages_needing_ocr(path):
    """How many pages have (almost) no selectable text, i.e. are scanned images."""
    with pymupdf.open(path) as pdf:
        return sum(len(page.get_text().strip()) < config.OCR_MIN_CHARS for page in pdf)


def ocr_findings(ocr_pages):
    """A review finding when any of the original was read by OCR: recognition errors can change
    numbers and warnings, so the reviewer checks those against the PDF itself."""
    if not ocr_pages:
        return []
    return [{"type": "ocr_source_text", "severity": "review",
             "detail": f"{ocr_pages} page(s) of the original are scanned images read by OCR. Check numbers, "
                       "units and warnings against the PDF; recognition errors are possible."}]


def no_text_detail(where):
    if ocr_available():
        return f"No text found {where}, even with OCR. Check the scan quality."
    return (f"No selectable text found {where}, and OCR is not available on this server "
            "(install Tesseract, or use the Docker image, which includes it).")


def extract_document_text(stored_path: str, scope: str, target_page: int | None,
                          max_pages: int | None = None):
    """Extract text from the immutable uploaded PDF; never modify the source."""
    try:
        with pymupdf.open(stored_path) as pdf:
            if len(pdf) == 0:
                raise HTTPException(status_code=422, detail="The PDF has no pages.")
            if scope == "full" and max_pages and len(pdf) > max_pages:
                raise HTTPException(
                    status_code=413,
                    detail=f"The PDF has {len(pdf)} pages; full-document revision supports up to "
                           f"{max_pages}. Revise one page at a time instead.",
                )

            if scope == "page":
                if target_page is None:
                    raise HTTPException(
                        status_code=400,
                        detail="For page scope, provide target_page (starting at 1).",
                    )
                if target_page < 1 or target_page > len(pdf):
                    raise HTTPException(
                        status_code=400,
                        detail=f"target_page must be between 1 and {len(pdf)}.",
                    )
                text = page_text(pdf[target_page - 1], stored_path)
                if not text:
                    raise HTTPException(status_code=422, detail=no_text_detail("on that page"))
                return text, target_page

            pages = [
                f"[PAGE {index + 1}]\n{page_text(page, stored_path)}"
                for index, page in enumerate(pdf)
            ]
            text = "\n\n".join(pages).strip()
            if not "".join(page.split("\n", 1)[1] for page in pages).strip():
                raise HTTPException(status_code=422, detail=no_text_detail("in this PDF"))
            return text, None
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not extract PDF text")
        raise HTTPException(
            status_code=422,
            detail=f"Could not read PDF text: {type(exc).__name__}.",
        ) from exc


def render_draft_pdf(header_lines, content):
    """Flow the draft text across A4 pages. This is a text rendering of the draft,
    not a reconstruction of the original PDF layout."""
    body = "".join(
        f"<p>{html.escape(line) or '&nbsp;'}</p>" for line in content.splitlines()
    )
    header = "".join(f"<p><b>{html.escape(line)}</b></p>" for line in header_lines)
    story = pymupdf.Story(
        html=f"{header}<hr/>{body}",
        user_css="p { font-family: sans-serif; font-size: 10pt; margin: 0 0 3pt 0; }",
    )
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    page = pymupdf.paper_rect("a4")
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(page + (50, 50, -50, -50))
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()
