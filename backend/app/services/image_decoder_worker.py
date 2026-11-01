"""Private, disposable image decoder. Run as a script, never in a web worker."""
import json
import math
from pathlib import Path
import resource
import sys
import warnings
import os
import signal
import ctypes

if os.environ.get('GC_DECODER_PARENT_PID'):
    ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0)
    if os.getppid() != int(os.environ['GC_DECODER_PARENT_PID']):
        os.kill(os.getpid(), signal.SIGKILL)

# Apply limits before importing native codecs. The parent also enforces wall time.
signal.alarm(12)  # Independent deadline if the supervising process is suspended.
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_METADATA_BYTES = 256 * 1024
MAX_OCR_PIXELS = 4_000_000
MAX_OCR_SIDE = 4096
FORMATS = ('JPEG', 'PNG', 'GIF', 'WEBP', 'HEIF')


class RejectedImage(Exception):
    pass


def reject(code):
    raise RejectedImage(code)


def main(source, destination, mode):
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener
    register_heif_opener(decode_threads=1, thumbnails=False, aux_images=False, depth_images=False)
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    if Path(source).stat().st_size > MAX_FILE_BYTES:
        reject('file_too_large')
    with Image.open(source, formats=FORMATS) as opened:
        width, height = opened.size
        if width <= 0 or height <= 0 or width * height > MAX_PIXELS or max(width, height) > 12000:
            reject('image_too_large')
        if sum(len(value.encode('utf-8')) if isinstance(value, str) else len(value)
               for value in opened.info.values() if isinstance(value, (bytes, str))) > MAX_METADATA_BYTES:
            reject('metadata_too_large')
        frames = getattr(opened, 'n_frames', 1)
        if frames > 100 or frames * width * height > 100_000_000:
            reject('too_many_frames')
        # Only the first frame is used for OCR. Original non-HEIF uploads stay intact.
        opened.seek(0)
        opened.load()
        image = ImageOps.exif_transpose(opened)
        try:
            if mode == 'ocr':
                width, height = image.size
                scale = min(max(1, 1500 / min(width, height)),
                            math.sqrt(MAX_OCR_PIXELS / (width * height)),
                            MAX_OCR_SIDE / max(width, height))
                size = (max(1, int(width * scale)), max(1, int(height * scale)))
                image = image.convert('RGB')
                if image.size != size:
                    image = image.resize(size, Image.Resampling.LANCZOS)
                Path(destination).write_bytes(image.tobytes())
            elif mode == 'jpeg':
                image = image.convert('RGB')
                image.save(destination, format='JPEG', quality=90, optimize=True,
                           exif=b'', icc_profile=None, comment=b'', xmp=b'')
                if Path(destination).stat().st_size > MAX_FILE_BYTES:
                    reject('file_too_large')
            elif mode != 'check':
                reject('invalid_image')
            print(json.dumps({'size': image.size, 'format': opened.format}))
        finally:
            image.close()


if __name__ == '__main__':
    try:
        main(*sys.argv[1:])
    except RejectedImage as exc:
        print(json.dumps({'error': str(exc)})); sys.exit(2)
    except MemoryError:
        print(json.dumps({'error': 'resource_limit'})); sys.exit(2)
    except Exception as exc:
        code = 'image_too_large' if type(exc).__name__ in (
            'DecompressionBombError', 'DecompressionBombWarning') else 'invalid_image'
        print(json.dumps({'error': code})); sys.exit(2)
