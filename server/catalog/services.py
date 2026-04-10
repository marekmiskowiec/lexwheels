from __future__ import annotations

import io
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from PIL import Image, UnidentifiedImageError

from .models import HotWheelsModel


class CatalogImageImportError(Exception):
    pass


IMAGE_FIELD_MAP = {
    'generic': ('local_photo_path', 'photo_url'),
    'short_card': ('short_card_local_photo_path', 'short_card_photo_url'),
    'long_card': ('long_card_local_photo_path', 'long_card_photo_url'),
    'loose': ('loose_local_photo_path', 'loose_photo_url'),
}

VARIANT_WIDTHS = {
    'thumb': 320,
    'preview': 960,
    'detail': 1400,
}


def import_catalog_image_from_url(model_obj: HotWheelsModel, packaging_state: str, source_url: str) -> str:
    if packaging_state not in IMAGE_FIELD_MAP:
        raise CatalogImageImportError('Nieobsługiwany wariant zdjęcia.')
    if packaging_state != 'generic' and packaging_state not in model_obj.available_packaging_states:
        raise CatalogImageImportError('Ten wariant zdjęcia nie jest dostępny dla modelu.')

    payload = download_image_bytes(source_url)
    image = open_downloaded_image(payload)
    relative_path = build_manual_image_relative_path(model_obj, packaging_state)
    generate_image_variants_from_image(image, relative_path)

    local_attr, url_attr = IMAGE_FIELD_MAP[packaging_state]
    previous_relative_path = (getattr(model_obj, local_attr) or '').strip()
    if previous_relative_path and previous_relative_path != relative_path:
        delete_image_artifacts(previous_relative_path)

    setattr(model_obj, local_attr, relative_path)
    setattr(model_obj, url_attr, '')
    model_obj.save(update_fields=[local_attr, url_attr])
    return relative_path


def download_image_bytes(source_url: str) -> bytes:
    request = Request(source_url, headers={'User-Agent': 'LexWheelsBot/1.0'})
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read()
    except Exception as exc:
        raise CatalogImageImportError('Nie udało się pobrać obrazu z podanego URL.') from exc
    if not payload:
        raise CatalogImageImportError('Pobrany plik jest pusty.')
    return payload


def open_downloaded_image(payload: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(payload))
        image.load()
        return image
    except (UnidentifiedImageError, OSError) as exc:
        raise CatalogImageImportError('Podany URL nie zwrócił poprawnego obrazu.') from exc


def build_manual_image_relative_path(model_obj: HotWheelsModel, packaging_state: str) -> str:
    return str(
        Path('images')
        / 'manual'
        / str(model_obj.year or 'unknown')
        / f'{model_obj.app_id}-{packaging_state}-{uuid.uuid4().hex[:10]}.webp'
    )


def generate_image_variants_from_image(source_image: Image.Image, relative_path: str) -> None:
    for variant_name, width in VARIANT_WIDTHS.items():
        destination_relative_path = HotWheelsModel.build_image_variant_relative_path(relative_path, variant_name)
        destination_path = settings.MEDIA_ROOT / destination_relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        image = source_image.copy()
        if image.mode not in ('RGB', 'RGBA'):
            image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
        image.thumbnail((width, width * 10), Image.Resampling.LANCZOS)
        image.save(destination_path, format='WEBP', quality=82, method=6)


def delete_image_artifacts(relative_path: str) -> None:
    for variant_name in HotWheelsModel.IMAGE_VARIANT_NAMES:
        variant_relative_path = HotWheelsModel.build_image_variant_relative_path(relative_path, variant_name)
        variant_path = settings.MEDIA_ROOT / variant_relative_path
        if variant_path.exists():
            variant_path.unlink()


def clear_catalog_image(model_obj: HotWheelsModel, packaging_state: str) -> None:
    if packaging_state not in IMAGE_FIELD_MAP:
        raise CatalogImageImportError('Nieobsługiwany wariant zdjęcia.')
    if packaging_state != 'generic' and packaging_state not in model_obj.available_packaging_states:
        raise CatalogImageImportError('Ten wariant zdjęcia nie jest dostępny dla modelu.')

    local_attr, url_attr = IMAGE_FIELD_MAP[packaging_state]
    image_reference = {
        'local_path': getattr(model_obj, local_attr, ''),
        'url': getattr(model_obj, url_attr, ''),
    }
    image_signature = model_obj.image_reference_signature(image_reference)
    generic_local_attr, generic_url_attr = IMAGE_FIELD_MAP['generic']
    generic_reference = model_obj.generic_image_reference()
    generic_signature = model_obj.image_reference_signature(generic_reference)
    relative_path = (getattr(model_obj, local_attr) or '').strip()
    if relative_path:
        delete_image_artifacts(relative_path)

    setattr(model_obj, local_attr, '')
    setattr(model_obj, url_attr, '')
    update_fields = [local_attr, url_attr]

    if packaging_state != 'generic' and generic_signature != ('', '') and generic_signature == image_signature:
        generic_relative_path = (getattr(model_obj, generic_local_attr) or '').strip()
        if generic_relative_path and generic_relative_path != relative_path:
            delete_image_artifacts(generic_relative_path)
        setattr(model_obj, generic_local_attr, '')
        setattr(model_obj, generic_url_attr, '')
        update_fields.extend([generic_local_attr, generic_url_attr])

    model_obj.save(update_fields=update_fields)
