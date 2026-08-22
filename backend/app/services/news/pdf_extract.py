"""PDF text extraction for uploaded newspapers / broker research.

Two-tier by design, matching LLD 06 §6:

  1. **Digital PDFs** (real text layer) -> PyMuPDF `get_text` directly. Cheap, exact.
  2. **Image/scanned PDFs** (e.g. The Economic Times e-paper, which is one full-page
     image per page, zero text) -> render page to a high-DPI bitmap, then Tesseract OCR.

We auto-detect per page: if the embedded text layer is empty we fall back to OCR, so a
mixed document (some digital pages, some scanned) still extracts fully.

OCR notes for multi-column newsprint:
  - Render at ~300 DPI. The source pages are ~2748x4278px; 300 DPI keeps small body
    fonts legible to Tesseract without ballooning memory.
  - PSM 3 (fully automatic page segmentation) lets Tesseract find the column blocks
    itself, which beats forcing a single column on a 4-6 column tabloid.
  - Grayscale + light upscaling improves recall on thin newsprint type.

Kept dependency-light and DB-free so it unit-tests like `engine.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Render scale: 72 dpi is PDF native. 200 dpi (~2.8x) keeps newsprint body fonts
# legible without upscaling far past the source image's own resolution.
_OCR_DPI = 200
_PDF_NATIVE_DPI = 72

# A page whose embedded text layer has fewer than this many chars is treated as
# "not really a text page" and sent to OCR.
_MIN_TEXT_LAYER_CHARS = 20


@dataclass
class PageText:
    page: int  # 1-indexed
    text: str
    method: str  # "text-layer" | "ocr" | "empty"
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


@dataclass
class ExtractResult:
    source: str
    page_count: int
    pages: list[PageText] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)

    @property
    def methods(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.pages:
            out[p.method] = out.get(p.method, 0) + 1
        return out


def _ocr_page(page, dpi: int = _OCR_DPI) -> str:
    """Render a PyMuPDF page to a bitmap and OCR it with Tesseract."""
    import io

    import pytesseract  # lazy: only needed on the OCR path
    from PIL import Image

    # We render our own trusted, local PDFs; the pixel budget is bounded by _OCR_DPI,
    # so lift PIL's decompression-bomb guard (it targets untrusted downloaded images).
    Image.MAX_IMAGE_PIXELS = None

    zoom = dpi / _PDF_NATIVE_DPI
    import fitz  # noqa: F401  (pymupdf; imported here to keep module import cheap)

    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    # PSM 3 = automatic page segmentation with OSD off; good for multi-column layouts.
    return pytesseract.image_to_string(img, config="--oem 1 --psm 3")


def extract_pdf(
    data: bytes,
    *,
    ocr_fallback: bool = True,
    pages: list[int] | None = None,
    dpi: int = _OCR_DPI,
    max_workers: int = 4,
) -> ExtractResult:
    """Extract text from a PDF.

    Args:
        data: raw PDF bytes.
        ocr_fallback: OCR pages that have no usable text layer.
        pages: optional 1-indexed page numbers to limit to (for testing / previews).
        dpi: OCR render resolution.
        max_workers: parallel page workers on the OCR path.
    """
    import fitz

    from concurrent.futures import ThreadPoolExecutor

    doc = fitz.open(stream=data, filetype="pdf")
    result = ExtractResult(source="pdf", page_count=doc.page_count)

    wanted = set(pages) if pages else None
    targets = [i for i in range(doc.page_count) if wanted is None or (i + 1) in wanted]

    def do_page(i: int) -> PageText:
        page = doc[i]
        pno = i + 1
        layer = page.get_text("text").strip()
        if len(layer) >= _MIN_TEXT_LAYER_CHARS:
            return PageText(page=pno, text=layer, method="text-layer")
        if not ocr_fallback:
            return PageText(page=pno, text="", method="empty")
        ocr = _ocr_page(page, dpi=dpi).strip()
        return PageText(page=pno, text=ocr, method="ocr" if ocr else "empty")

    # Render+OCR pages in parallel (same pattern as market_data quotes). Tesseract is
    # single-threaded per call, so a small pool overlaps CPU well without thrashing RAM.
    if len(targets) > 1 and ocr_fallback:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            result.pages = sorted(ex.map(do_page, targets), key=lambda p: p.page)
    else:
        result.pages = [do_page(i) for i in targets]

    doc.close()
    return result


def extract_pdf_file(
    path: str,
    *,
    ocr_fallback: bool = True,
    pages: list[int] | None = None,
    dpi: int = _OCR_DPI,
    max_workers: int = 4,
) -> ExtractResult:
    with open(path, "rb") as f:
        return extract_pdf(
            f.read(), ocr_fallback=ocr_fallback, pages=pages, dpi=dpi, max_workers=max_workers
        )
