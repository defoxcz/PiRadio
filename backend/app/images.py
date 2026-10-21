"""Omezený příjem obrázků; ukládáme pouze nově zakódované pixely."""
from io import BytesIO
from pathlib import Path
import warnings
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import HTTPException

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def save_image(content: bytes, directory: Path) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ValueError('Nepodporovaný formát')
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError('Příliš velké rozlišení')
                source.load()
                image = ImageOps.exif_transpose(source)
                image.thumbnail((1024, 1024))
                rgba = image.convert('RGBA')
                flattened = Image.new('RGB', rgba.size, '#142026')
                flattened.paste(rgba, mask=rgba.getchannel('A'))
                encoded = BytesIO()
                flattened.save(encoded, format='JPEG', quality=85)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'Vyberte platný obrázek JPG, PNG nebo WebP s rozlišením nejvýše 16 megapixelů.')
    filename = f'{uuid4().hex}.jpg'
    target = directory / filename
    try:
        # Náhodný název, žádné přepisování cizích souborů ani původní metadata.
        with target.open('xb') as output:
            output.write(encoded.getvalue())
    except OSError:
        target.unlink(missing_ok=True)
        raise HTTPException(507, 'Obrázek nelze uložit. Zkontrolujte místo na disku serveru.')
    return f'/media/{filename}'
