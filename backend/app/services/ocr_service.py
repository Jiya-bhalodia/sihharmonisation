"""Offline OCR adapter for scanned PDFs using Tesseract and Poppler."""
from io import BytesIO
from statistics import mean

from app.config import get_settings


class OcrUnavailableError(RuntimeError):
    """Raised when the local OCR runtime or required language data is missing."""


def ocr_pdf(file_bytes: bytes, page_count: int) -> tuple[str, float | None]:
    """OCR up to the configured page limit; no data is sent to a remote service."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        from pytesseract import Output
    except ImportError as error:
        raise OcrUnavailableError(
            "Scanned-PDF OCR needs pdf2image, pytesseract, Poppler, and Tesseract. "
            "Install the project OCR dependencies or use the Docker image."
        ) from error

    settings = get_settings()
    pages_to_process = min(max(page_count, 0), max(settings.OCR_MAX_PAGES, 1))
    if pages_to_process == 0:
        return "", None

    try:
        images = convert_from_bytes(
            file_bytes,
            first_page=1,
            last_page=pages_to_process,
            dpi=settings.OCR_DPI,
            fmt="png",
            thread_count=1,
            size=2200,
        )
    except Exception as error:
        message = str(error).lower()
        if "poppler" in message or error.__class__.__name__ in {
            "PDFInfoNotInstalledError", "PDFPageCountError", "PDFPopplerTimeoutError",
        }:
            raise OcrUnavailableError(
                "Local PDF OCR could not start because Poppler is missing or could not read this PDF."
            ) from error
        raise

    languages = settings.OCR_LANGUAGES.strip() or "eng"
    page_texts = []
    confidences = []
    for image in images:
        try:
            data = pytesseract.image_to_data(
                image, lang=languages, config="--psm 6", output_type=Output.DICT
            )
        except pytesseract.TesseractNotFoundError as error:
            raise OcrUnavailableError(
                "Tesseract is not installed. Install it locally or use the project Docker image."
            ) from error
        except pytesseract.TesseractError as error:
            if languages != "eng":
                try:
                    data = pytesseract.image_to_data(
                        image, lang="eng", config="--psm 6", output_type=Output.DICT
                    )
                except pytesseract.TesseractError as fallback_error:
                    raise OcrUnavailableError(
                        "Tesseract language data is missing. Install the configured language packs."
                    ) from fallback_error
            else:
                raise OcrUnavailableError(
                    "Tesseract could not process this page; check that its English language data is installed."
                ) from error
        words = [word.strip() for word in data.get("text", []) if word and word.strip()]
        page_texts.append(" ".join(words))
        for value in data.get("conf", []):
            try:
                confidence = float(value)
                if confidence >= 0:
                    confidences.append(confidence)
            except (TypeError, ValueError):
                continue

    return "\n".join(page_texts).strip(), round(mean(confidences), 1) if confidences else None
