"""Bounded thumbnail conversion for volatile LCD picture memory."""
from io import BytesIO
import posixpath
import time
import logging
from urllib.parse import quote
from PIL import Image, ImageChops
from petrel.features.files.metadata import PreviewData, details_from_metadata

MIN_FOREGROUND_LUMA = 48
MAX_CANDIDATES = 4


class NoThumbnail(ValueError):
    """Positive metadata evidence that this file has no usable image path."""



def _protect_dark_foreground(rgba):
    """Reserve black for transparency; lift dark model pixels before alpha blend."""
    pixels = []
    for r, g, b, alpha in rgba.getdata():
        if not alpha:
            pixels.append((0, 0, 0, 0))
            continue
        luma = (299 * r + 587 * g + 114 * b) // 1000
        while luma < MIN_FOREGROUND_LUMA:
            lift = MIN_FOREGROUND_LUMA - luma
            r, g, b = (min(255, c + lift) for c in (r, g, b))
            luma = (299 * r + 587 * g + 114 * b) // 1000
        pixels.append((r, g, b, alpha))
    protected = Image.new('RGBA', rgba.size)
    protected.putdata(pixels)
    return protected


def _opaque_canvas(size):
    """For panels that draw SRAM JPEGs opaque, black backing would stay visible.

    Compose the picture on what is behind it instead: the UI background, or for
    the 88 px print tile the tile artwork itself with background-coloured corners.
    """
    from petrel.ui.theme import BACKGROUND_COLOR
    # Centre of the RGB565 step: small JPEG errors still decode to the exact UI colour.
    background = ((BACKGROUND_COLOR >> 11) * 8 + 4, ((BACKGROUND_COLOR >> 5) & 63) * 4 + 2,
                  (BACKGROUND_COLOR & 31) * 8 + 4)
    if size == 88:
        from petrel.artwork.icon_library import SOURCE_DIRECTORY
        from petrel.artwork.resources import ICON_PREVIEW_BACKING
        try:
            with Image.open(SOURCE_DIRECTORY / f'{ICON_PREVIEW_BACKING:03d}.jpg') as tile:
                tile = tile.convert('RGB')
            if tile.size == (size, size):
                r, g, b = tile.split()
                dark = ImageChops.lighter(ImageChops.lighter(r, g), b).point(
                    [255 if v < 24 else 0 for v in range(256)])
                tile.paste(background, (0, 0, size, size), dark)
                return tile
        except OSError:
            pass
    return Image.new('RGB', (size, size), background)


def image_jpeg(data, size=128, *, opaque=False):
    """Reserve black backing for filtered drawing, protecting dark model details.

    ``opaque`` (the panel's OPAQUE_SRAM_JPEG) composes the thumbnail on the UI
    background instead, for panels that cannot filter black.
    """
    if size not in (88, 128):
        raise ValueError('Unsupported panel thumbnail size')
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 4_000_000:
            raise ValueError('Thumbnail too large')
        source.thumbnail((size, size), Image.Resampling.LANCZOS)
        rgba = _protect_dark_foreground(source.convert('RGBA'))
        canvas = _opaque_canvas(size) if opaque else Image.new('RGB', (size, size), 'black')
        canvas.paste(rgba, ((size-rgba.width)//2, (size-rgba.height)//2), rgba)
    output = BytesIO()
    # Opaque thumbnails: maximum 4:2:0 quality keeps the colour fringe at model edges small.
    canvas.save(output, format='JPEG', quality=100 if opaque else 94, subsampling=2,
                progressive=False, optimize=False)
    jpeg = output.getvalue()
    if len(jpeg) > 32768:
        raise ValueError('JPEG exceeds LCD SRAM')
    return jpeg


def load_thumbnail(client, filename, metadata=None, size=128, *, opaque=False):
    started = time.monotonic()
    if metadata is None:
        metadata = client.get('/server/files/metadata?filename=' + quote(filename, safe=''))['result']
    thumbs = metadata.get('thumbnails', [])
    candidates = [t for t in thumbs if isinstance(t, dict) and isinstance(t.get('relative_path'), str)
                  and all(isinstance(t.get(k), int) and 0 < t[k] <= 4080 for k in ('width', 'height'))]
    # Prefer a source large enough for the preview, rather than a tiny icon.
    candidates.sort(key=lambda t: (max(t['width'], t['height']) < 128,
                                   abs(max(t['width'], t['height'])-128)))
    attempts = 0
    for thumb in candidates:
        relative = thumb['relative_path']
        path = posixpath.normpath(posixpath.join(posixpath.dirname(filename), relative))
        if relative.startswith('/') or path.startswith('../') or path == '..':
            continue
        if attempts >= MAX_CANDIDATES:
            break
        attempts += 1
        try:
            data = client.get_bytes('/server/files/gcodes/' + quote(path, safe='/'), max_bytes=2_000_000)
            downloaded = time.monotonic()
            jpeg = image_jpeg(data,size=size,opaque=opaque)
        except Exception as error:
            logging.info('Thumbnail candidate unavailable: %s', type(error).__name__)
            continue
        logging.info('Thumbnail %s: download %.3fs, conversion %.3fs, %d JPEG bytes',
                     filename, downloaded-started, time.monotonic()-downloaded, len(jpeg))
        return jpeg
    if attempts:
        raise ValueError('Thumbnail candidates unavailable')
    raise NoThumbnail('No thumbnail')


def load_preview(client, filename, size=128, *, opaque=False):
    metadata = client.get('/server/files/metadata?filename=' + quote(filename, safe=''))['result']
    details = details_from_metadata(metadata)
    retryable = True
    try:
        jpeg = load_thumbnail(client, filename, metadata=metadata, size=size, opaque=opaque)
    except NoThumbnail:
        jpeg, retryable = None, False
    except Exception as error:
        logging.info('Thumbnail unavailable %s: %s', filename, error)
        jpeg = None
    return PreviewData(jpeg, details, retryable=retryable)
