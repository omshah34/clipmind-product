from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path

from core.config import settings
from services.openai_client import create_chat_completion

logger = logging.getLogger(__name__)


@dataclass
class DocumentParseResult:
    text: str
    parser: str
    ocr_used: bool
    page_count: int


class DocumentParserError(RuntimeError):
    pass


def _extract_pdf_text(path: Path) -> tuple[str, int]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise DocumentParserError("pypdf is not installed for PDF text extraction.") from exc

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts).strip(), len(reader.pages)


def _render_pdf_pages(path: Path) -> list[str]:
    try:
        import fitz  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise DocumentParserError("PyMuPDF is not installed for OCR fallback.") from exc

    document = fitz.open(str(path))
    encoded_pages: list[str] = []
    try:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            encoded_pages.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
    finally:
        document.close()
    return encoded_pages


def _ocr_images(encoded_images: list[str]) -> str:
    if not settings.groq_api_key:
        raise DocumentParserError("GROQ_API_KEY is required for OCR fallback.")

    pages: list[str] = []
    for encoded_image in encoded_images:
        try:
            completion = create_chat_completion(
                preferred_model=settings.brand_guide_ocr_model,
                vision=True,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract all visible document text exactly. Return plain text only.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract the text from this scanned document page."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{encoded_image}"},
                            },
                        ],
                    },
                ],
            )
        except Exception as exc:
            raise DocumentParserError(f"OCR fallback failed: {exc}") from exc

        response = completion.response
        content = response.choices[0].message.content if response.choices else ""
        if content:
            pages.append(content.strip())

    return "\n\n".join(page for page in pages if page).strip()


def parse_brand_guide(path: Path) -> DocumentParseResult:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, page_count = _extract_pdf_text(path)
        if text:
            return DocumentParseResult(text=text, parser="pypdf", ocr_used=False, page_count=page_count)

        encoded_pages = _render_pdf_pages(path)
        text = _ocr_images(encoded_pages)
        if not text:
            raise DocumentParserError("Unable to extract any text from the uploaded PDF.")
        return DocumentParseResult(text=text, parser="groq_vision", ocr_used=True, page_count=len(encoded_pages))

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        text = _ocr_images([base64.b64encode(path.read_bytes()).decode("ascii")])
        if not text:
            raise DocumentParserError("Unable to extract any text from the uploaded image.")
        return DocumentParseResult(text=text, parser="groq_vision", ocr_used=True, page_count=1)

    raise DocumentParserError("Only PDF and image brand guides are supported.")
