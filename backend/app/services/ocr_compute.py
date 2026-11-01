"""Pure recognition pipeline, executed only inside a bounded OCR child process."""
import json
import logging
import os
import re as _re
import sys

logger = logging.getLogger(__name__)


def extract_image_text(filepath):
    OCR_TEXT_MAX_CHARS = 10_000
    MIN_OCR_CONFIDENCE = 40   # discard tesseract words below this threshold
    _CONTROL_CHARS = dict.fromkeys(range(32), None)
    _CONTROL_CHARS.pop(9)   # keep tab
    _CONTROL_CHARS.pop(10)  # keep newline
    _CONTROL_CHARS.pop(13)  # keep carriage return
    _STRIP_TABLE = str.maketrans(_CONTROL_CHARS)

    from PIL import Image, ImageOps, ImageFilter
    import pytesseract
    import numpy as np

    # Decode/transpose/resize outside the web process, under CPU, memory and
    # wall-time limits. Only bounded RGB pixels enter NumPy/Pillow below.
    from app.services.image_decoder import image_for_ocr
    img = image_for_ocr(filepath)

    # 2. Normalise colour mode
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    # 3. Convert to grayscale
    gray = img.convert('L')

    # The isolated decoder targets a 1500px short side, capped at 4MP/4096px
    # so a very narrow image cannot expand into an enormous OCR buffer.

    # 5. Local illumination normalisation — the most impactful step for
    #    phone photos of receipts.  A heavy Gaussian blur (radius 25) gives
    #    a smooth background-illumination estimate; dividing each pixel by
    #    that estimate then scaling to 128 cancels shadows, flash gradients,
    #    and paper curvature so the text contrast is equalised across the
    #    whole image.
    gray_arr = np.array(gray, dtype=np.float32)
    bg_arr = np.array(
        gray.filter(ImageFilter.GaussianBlur(radius=25)),
        dtype=np.float32,
    )
    normalized_arr = np.clip(
        gray_arr / (bg_arr + 1.0) * 128.0, 0, 255
    ).astype(np.uint8)
    gray = Image.fromarray(normalized_arr)

    # 6. Auto-contrast stretch — spreads the normalised pixel values to
    #    the full 0–255 range; 1% clip discards extreme outliers.
    gray = ImageOps.autocontrast(gray, cutoff=1)

    # 7. Median filter — removes salt-and-pepper noise without blurring
    #    the character strokes.
    gray = gray.filter(ImageFilter.MedianFilter(size=3))

    # 8. Unsharp mask — make character edges crisp before binarisation.
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.5, percent=200, threshold=3))

    # 9. Histogram-based binarisation — compute the 55th-percentile
    #    brightness value and use it as the black/white threshold.
    #    The majority of a receipt is bright paper (white) and the
    #    minority is dark text (black) so this percentile separates them
    #    cleanly while clamped to [80, 220] for safety.
    hist = gray.histogram()  # 256-bucket frequency list
    total = sum(hist)
    target = total * 0.55
    cumsum, threshold = 0, 128
    for i, count in enumerate(hist):
        cumsum += count
        if cumsum >= target:
            threshold = i
            break
    threshold = max(80, min(220, threshold))
    binary = gray.point(lambda p: 255 if p > threshold else 0)

    # 10. OSD rotation — detect and correct text orientation.
    #     Run on the binarised image for better OSD accuracy.
    #     OSD can fail on low-text or highly-stylised images; ignore errors.
    try:
        osd = pytesseract.image_to_osd(
            binary,
            output_type=pytesseract.Output.DICT,
            config='--psm 0',
            timeout=5,
        )
        rotate_angle = osd.get('rotate', 0)
        if rotate_angle:
            binary = binary.rotate(rotate_angle, expand=True)
            logger.debug('Rotated receipt %d degrees', rotate_angle)
    except Exception:
        pass  # OSD unavailable or too little text — continue without rotation

    # 11. Confidence-filtered OCR via image_to_data.
    #     image_to_data returns per-word bounding boxes and confidence
    #     scores (0–100).  We drop any word with confidence < MIN_OCR_CONFIDENCE
    #     to eliminate camera-noise artefacts, then re-assemble the output
    #     line-by-line preserving the original block/paragraph/line structure.
    def _ocr_filtered(image, psm):
        data = pytesseract.image_to_data(
            image,
            lang='eng+ron+spa',
            config=f'--oem 1 --psm {psm} --dpi 300',
            output_type=pytesseract.Output.DICT,
            timeout=15,
        )
        lines: dict = {}
        for i in range(len(data['text'])):
            word = (data['text'][i] or '').strip()
            conf = int(data['conf'][i])
            if not word or conf < 0:
                continue
            key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            if key not in lines:
                lines[key] = []
            if conf >= MIN_OCR_CONFIDENCE:
                lines[key].append(word)
            # Low-confidence words are silently discarded
        text_lines = [
            ' '.join(words)
            for key in sorted(lines)
            for words in [lines[key]]
            if words
        ]
        return '\n'.join(text_lines)

    # PSM 4 = single column of variable-size text — ideal for receipts.
    # Fall back to PSM 6 (uniform block) if PSM 4 yields very little.
    raw = _ocr_filtered(binary, psm=4)
    if len(raw.split()) < 5:
        raw = _ocr_filtered(binary, psm=6)

    cleaned = raw.strip().translate(_STRIP_TABLE)
    # Collapse 3+ consecutive blank lines into a single blank line
    cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned)
    ocr_text = cleaned[:OCR_TEXT_MAX_CHARS] or None

    return ocr_text


def extract_pdf_text(filepath):
    from pypdf import PdfReader
    reader = PdfReader(filepath)
    text = '\n'.join(page.extract_text() or '' for page in reader.pages[:10])
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t\r')
    text = _re.sub(r'[ \t]{2,}', ' ', text.strip())
    return _re.sub(r'\n{3,}', '\n\n', text)[:10000] or None


def main():
    # Linux deployment: independently bound a child even if its worker disappears.
    import ctypes
    import resource
    import signal
    expected_parent = int(os.environ['GC_OCR_PARENT_PID'])
    def terminate(*_):
        os.killpg(os.getpgrp(), signal.SIGKILL)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGALRM, terminate)
    ctypes.CDLL(None).prctl(1, signal.SIGTERM, 0, 0, 0)  # PR_SET_PDEATHSIG
    if os.getppid() != expected_parent:
        terminate()
    signal.alarm(90)
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    kind, filepath = sys.argv[1:]
    if os.path.getsize(filepath) > 10 * 1024**2:
        raise ValueError('Input too large')
    text = extract_pdf_text(filepath) if kind == 'pdf' else extract_image_text(filepath)
    print(json.dumps({'text': text or ''}, ensure_ascii=False))


if __name__ == '__main__':
    main()
