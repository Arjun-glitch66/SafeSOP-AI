
import hashlib
import shutil
from pathlib import Path

import pymupdf

PROJECT_DIR = Path(__file__).resolve().parent.parent
ORIGINALS_DIR = PROJECT_DIR / "data" / "originals"
GENERATED_DIR = PROJECT_DIR / "data" / "generated"

ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def calculate_file_hash(file_path):
    """Calculate SHA-256 so we can identify the original file."""
    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            digest.update(chunk)

    return digest.hexdigest()


def store_original(uploaded_file):
    """
    Save an uploaded PDF without overwriting an existing original.
    uploaded_file must have a name and support read().
    """
    filename = Path(uploaded_file.name).name

    if Path(filename).suffix.lower() != ".pdf":
        raise ValueError("Please upload a PDF file.")

    content = uploaded_file.read()

    if not content.startswith(b"%PDF-"):
        raise ValueError("The uploaded file is not a valid PDF.")

    file_hash = hashlib.sha256(content).hexdigest()

    # Reuse the stored copy if this exact file already exists.
    destination = ORIGINALS_DIR / f"{file_hash}.pdf"

    if not destination.exists():
        destination.write_bytes(content)

    return {
        "original_name": filename,
        "original_path": str(destination),
        "file_hash": file_hash,
    }


def extract_pdf_pages(file_path):
    """Return one extracted text string for each PDF page."""
    pages = []

    with pymupdf.open(file_path) as document:
        for page_number, page in enumerate(document, start=1):
            pages.append({
                "page_number": page_number,
                "text": page.get_text(sort=True).strip(),
            })

    return pages


def extract_single_page(file_path, page_number):
    """Page numbers supplied by the user start at 1."""
    pages = extract_pdf_pages(file_path)

    if page_number < 1 or page_number > len(pages):
        raise ValueError(
            f"Page must be between 1 and {len(pages)}."
        )

    return pages[page_number - 1]


def get_document_summary(file_path):
    pages = extract_pdf_pages(file_path)

    return {
        "page_count": len(pages),
        "pages_with_text": sum(
            1 for page in pages if page["text"]
        ),
        "total_characters": sum(
            len(page["text"]) for page in pages
        ),
        "pages": pages,
    }


def save_generated_pdf(source_path, output_path):
    """
    Create an exact PDF copy for version storage.
    This does not modify the original.
    """
    source = Path(source_path)
    output = Path(output_path)

    if not source.is_file():
        raise FileNotFoundError("Source PDF not found.")

    output.parent.mkdir(parents=True, exist_ok=True)

    if source.resolve() == output.resolve():
        raise ValueError("Output must not overwrite the source.")

    shutil.copy2(source, output)

    return str(output)
