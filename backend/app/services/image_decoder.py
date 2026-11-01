"""Bound untrusted codec/metadata work to a disposable Linux subprocess."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory


DECODE_TIMEOUT_SECONDS = 12
MAX_OCR_PIXELS = 4_000_000
_WORKER = Path(__file__).with_name('image_decoder_worker.py')
_ERRORS = {
    'invalid_image': 'Image could not be decoded safely.',
    'image_too_large': 'Image exceeds the 20 megapixel or 12000 pixel side limit.',
    'metadata_too_large': 'Image metadata exceeds the 256KB limit.',
    'too_many_frames': 'Image animation exceeds the frame limit.',
    'file_too_large': 'Processed image exceeds the 10MB file limit.',
    'resource_limit': 'Image processing exceeded its resource or time limit.',
}


class ImageDecodeError(ValueError):
    pass


def _decode(source, destination, mode):
    from app.services.decoder_slots import decoder_slot
    with decoder_slot():
        return _decode_in_slot(source, destination, mode)


def _decode_in_slot(source, destination, mode):
    process = subprocess.Popen(
        [sys.executable, str(_WORKER), str(source), str(destination), mode],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
        env={**os.environ, 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
             'GC_DECODER_PARENT_PID': str(os.getpid())},
    )
    try:
        output, _ = process.communicate(timeout=DECODE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise ImageDecodeError(_ERRORS['resource_limit']) from None
    if process.returncode < 0:
        raise ImageDecodeError(_ERRORS['resource_limit'])
    try:
        if len(output) > 4096:
            raise ValueError('Invalid decoder result')
        result = json.loads(output)
        if process.returncode or 'error' in result:
            raise ImageDecodeError(_ERRORS.get(result.get('error'), _ERRORS['invalid_image']))
        width, height = result['size']
        if not isinstance(width, int) or not isinstance(height, int) or min(width, height) <= 0:
            raise ValueError('Invalid decoder size')
        return result
    except (ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, ImageDecodeError):
            raise
        raise ImageDecodeError(_ERRORS['invalid_image']) from None


def validate_image(source):
    return _decode(source, '-', 'check')


def transcode_jpeg(source, destination):
    return _decode(source, destination, 'jpeg')


def image_for_ocr(source):
    from PIL import Image
    with TemporaryDirectory(prefix='gc-image-') as folder:
        output = Path(folder) / 'pixels.rgb'
        result = _decode(source, output, 'ocr')
        width, height = result['size']
        if width * height > MAX_OCR_PIXELS or max(width, height) > 4096:
            raise ImageDecodeError(_ERRORS['resource_limit'])
        pixels = output.read_bytes()
        if len(pixels) != width * height * 3:
            raise ImageDecodeError(_ERRORS['invalid_image'])
        # Only bounded RGB pixels cross the process boundary; no metadata/parser.
        return Image.frombytes('RGB', (width, height), pixels)
