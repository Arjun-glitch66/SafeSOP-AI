"""Reading the immutable original PDF and rendering drafts as PDF."""
import html
import io
import logging

import pymupdf
from fastapi import HTTPException

logger = logging.getLogger("safesop")


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
                page_text = pdf[target_page - 1].get_text(sort=True).strip()
                if not page_text:
                    raise HTTPException(
                        status_code=422,
                        detail="No selectable text found on that page. OCR is not implemented.",
                    )
                return page_text, target_page

            pages = [
                f"[PAGE {index + 1}]\n{page.get_text(sort=True).strip()}"
                for index, page in enumerate(pdf)
            ]
            text = "\n\n".join(pages).strip()
            if not text:
                raise HTTPException(
                    status_code=422,
                    detail="No selectable text found in this PDF. OCR is not implemented.",
                )
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
