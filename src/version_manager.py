
import hashlib
from pathlib import Path

from src.database import (
    register_original,
    create_generation_request,
    save_version,
    get_versions,
)
from src.document_parser import ORIGINALS_DIR, GENERATED_DIR


def sha256_file(file_path):
    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            digest.update(chunk)

    return digest.hexdigest()


def register_uploaded_document(uploaded_file):
    """Store and register the immutable original PDF."""

    from src.document_parser import store_original

    stored = store_original(uploaded_file)

    document_id = register_original(
        stored["original_name"],
        stored["original_path"],
        stored["file_hash"],
    )

    return {
        "document_id": document_id,
        **stored,
    }


def create_request(
    document_id,
    change_request,
    output_scope="full",
    target_page=None,
    target_section=None,
):
    return create_generation_request(
        document_id=document_id,
        change_request=change_request,
        output_scope=output_scope,
        target_page=target_page,
        target_section=target_section,
    )


def save_generated_version(
    document_id,
    request_id,
    original_name,
    generated_text,
    parent_version_id=None,
):
    """
    Save a text draft as a distinct version.

    This does not create a PDF. PDF export will be implemented
    separately so text drafts are not mistaken for finished PDFs.
    """

    existing_versions = get_versions(document_id)
    version_number = len(existing_versions) + 1

    safe_name = Path(original_name).stem
    version_name = f"{safe_name}_{version_number}"

    output_dir = GENERATED_DIR / str(document_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{version_name}.md"
    output_path.write_text(generated_text, encoding="utf-8")

    version_id = save_version(
        document_id=document_id,
        request_id=request_id,
        version_name=version_name,
        file_path=str(output_path),
        content=generated_text,
        parent_version_id=parent_version_id,
    )

    return {
        "version_id": version_id,
        "version_number": version_number,
        "version_name": version_name,
        "file_path": str(output_path),
        "content_hash": sha256_file(output_path),
    }


def list_document_versions(document_id):
    return get_versions(document_id)
