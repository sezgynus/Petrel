"""Encode the approved lossless spool frames for the managed DWIN library."""
from pathlib import Path
from PIL import Image

SOURCE = Path(__file__).resolve().parent
OUTPUT = SOURCE.parents[1] / 'icons'

if __name__ == '__main__':
    for frame in range(12):
        with Image.open(SOURCE / f'spool-{frame:02d}.png') as image:
            image.convert('RGB').save(
                OUTPUT / f'{188 + frame:03d}.jpg', 'JPEG',
                quality=84, subsampling=2, progressive=False, optimize=True)
