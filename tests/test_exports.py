"""Exports: values a reader copies out of a controlled document must survive text extraction."""
import pymupdf

from app.services import exports

# Hex can contain "ff", which proportional fonts turn into one ligature glyph (U+FB00).
LIGATURE_PRONE_HASH = "b4067f612b8c6bd5f1d0f3a18c114ec37754c638da3252643e48d67bedff0913"[:56] + "ffaffff0"


def record():
    return {
        "version": {"filename": "sop.pdf", "version_number": 2, "created_at": "2026-11-06T10:00:00",
                    "created_by": "alice", "model": "stub", "change_request": "use torque 20Nm",
                    "document_sha256": LIGATURE_PRONE_HASH},
        "approval": {"reviewer": "rita", "created_at": "2026-11-06T11:00:00", "feedback": "",
                     "evaluation_status": "pass_automated", "evaluator_version": "safe-sop-eval-1.4",
                     "source_sha256": LIGATURE_PRONE_HASH, "content_sha256": LIGATURE_PRONE_HASH},
        "reviews": [], "lineage": [], "draft": "1. Tighten to 20 Nm.", "summary": "",
    }


def test_pdf_export_hashes_extract_exactly_even_with_ligature_prone_letters():
    assert len(LIGATURE_PRONE_HASH) == 64
    with pymupdf.open(stream=exports.build_pdf(record()), filetype="pdf") as document:
        text = "".join(page.get_text() for page in document).replace("\n", "")
    assert LIGATURE_PRONE_HASH in text
    assert "ﬀ" not in text.split("SHA-256")[1][:80]  # no 'ff' ligature right after the label


def test_docx_export_contains_the_exact_hash():
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(exports.build_docx(record()))) as archive:
        assert LIGATURE_PRONE_HASH in archive.read("word/document.xml").decode()
