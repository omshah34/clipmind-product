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


def _ocr_single_image(encoded_image: str) -> str:
    if not settings.groq_api_key:
        raise DocumentParserError("GROQ_API_KEY is required for OCR fallback.")

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
    return content.strip() if content else ""


def _ocr_pdf_pages(path: Path, page_limit: int) -> tuple[str, int]:
    try:
        import fitz  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise DocumentParserError("PyMuPDF is not installed for OCR fallback.") from exc

    document = fitz.open(str(path))
    try:
        total_pages = document.page_count
        max_pages = max(1, page_limit)
        pages_to_scan = min(total_pages, max_pages)
        if total_pages > max_pages:
            logger.warning(
                "PDF page count %d exceeds OCR cap %d; scanning first %d pages only.",
                total_pages,
                max_pages,
                pages_to_scan,
            )

        parts: list[str] = []
        for page_index in range(pages_to_scan):
            page = document.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            encoded = base64.b64encode(pix.tobytes("png")).decode("ascii")
            page_text = _ocr_single_image(encoded)
            if page_text:
                parts.append(page_text)
        return "\n\n".join(parts).strip(), pages_to_scan
    finally:
        document.close()


def parse_brand_guide(path: Path) -> DocumentParseResult:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, page_count = _extract_pdf_text(path)
        if text:
            return DocumentParseResult(text=text, parser="pypdf", ocr_used=False, page_count=page_count)

        text, scanned_pages = _ocr_pdf_pages(path, settings.brand_guide_ocr_page_limit)
        if not text:
            raise DocumentParserError("Unable to extract any text from the uploaded PDF.")
        return DocumentParseResult(text=text, parser="groq_vision", ocr_used=True, page_count=scanned_pages)

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        text = _ocr_single_image(base64.b64encode(path.read_bytes()).decode("ascii"))
        if not text:
            raise DocumentParserError("Unable to extract any text from the uploaded image.")
        return DocumentParseResult(text=text, parser="groq_vision", ocr_used=True, page_count=1)

    raise DocumentParserError("Only PDF and image brand guides are supported.")
