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


# Common English function words — a dictionary-free "does this read as English" probe.
# Rotated/garbled OCR contains almost none of these; clean prose is dense with them.
_STOPWORDS = frozenset(
    "the and of to in for is that on with as are be by this it from at an or was "
    "will has have not its had which their can may also more than been".split()
)
_TOKEN_RE = None  # compiled lazily


def _readability(text: str) -> float:
    """Density of English function words among all word tokens — a scale-free
    "does this read as English" score in [0, 1]. Upright prose lands ~0.15-0.30;
    rotated/garbled OCR lands near 0 even when it emits many stray fragments, so
    density separates the two far more reliably than a raw count."""
    global _TOKEN_RE
    if _TOKEN_RE is None:
        import re

        _TOKEN_RE = re.compile(r"[a-z]+")
    toks = _TOKEN_RE.findall(text.lower())
    if len(toks) < 20:
        return 1.0  # too little text to judge; don't trigger a rotation retry
    return sum(1 for t in toks if t in _STOPWORDS) / len(toks)


_OCR_CONFIG = "--oem 1 --psm 3"
# Below this function-word density, a text-heavy page is almost certainly rotated or
# garbled; we retry the other orientations and keep the most readable result.
_MIN_READABILITY = 0.04


def _ocr_page(page, dpi: int = _OCR_DPI) -> str:
    """Render a PyMuPDF page to a bitmap and OCR it, self-correcting orientation.

    Newspaper e-papers occasionally print a continuation page (e.g. prospectus
    back-matter) rotated 180°/90°. Tesseract's PSM 3 doesn't auto-rotate, and its
    OSD is unreliable on dense pages, so instead of trusting OSD we OCR upright, and
    only if the result reads as garbled (very few English function words despite
    ample text) do we try the other 3 rotations and keep the most readable one. The
    expensive retry therefore fires only on the rare bad page.
    """
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

    text = pytesseract.image_to_string(img, config=_OCR_CONFIG)
    score = _readability(text)
    # Only bother retrying when there's real text volume but it doesn't read as English.
    if score < _MIN_READABILITY and len(text) > 200:
        best_text, best_score = text, score
        for angle in (180, 90, 270):
            cand = pytesseract.image_to_string(img.rotate(-angle, expand=True), config=_OCR_CONFIG)
            cscore = _readability(cand)
            if cscore > best_score:
                best_text, best_score = cand, cscore
        text = best_text
    return text


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
