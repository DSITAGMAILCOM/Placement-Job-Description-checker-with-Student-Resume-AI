import pymupdf


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from all pages of a PDF byte payload using PyMuPDF."""
    if not pdf_bytes:
        raise ValueError("Uploaded PDF file is empty.")

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not read PDF file: {exc}") from exc

    pages: list[str] = []
    try:
        for page in doc:
            text = page.get_text("text")
            if text:
                pages.append(text.strip())
    finally:
        doc.close()

    combined = "\n\n".join(p for p in pages if p)
    if not combined.strip():
        raise ValueError("No readable text found in the uploaded PDF.")
    return combined
