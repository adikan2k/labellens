"""What an uploaded label photo may be: JPEG, PNG or WebP by its first bytes, 5 MB at most,
one or two of them. The web app downscales to 1568 px first, so a real one is ~300 KB."""

from __future__ import annotations

from dataclasses import dataclass

MAX_IMAGES = 2
MAX_BYTES = 5 * 1024 * 1024


class ImageError(ValueError):
    """An upload the reader cannot take; the message says why, for a 422."""


@dataclass(frozen=True)
class Image:
    media_type: str
    data: bytes


def sniff(data: bytes) -> str | None:
    """The media type from the file's magic bytes; the declared type is not trusted."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def check(files: list[bytes]) -> list[Image]:
    if not files:
        raise ImageError("Add a photo of the label.")
    if len(files) > MAX_IMAGES:
        raise ImageError(f"At most {MAX_IMAGES} photos: the ingredients and the nutrition panel.")
    images = []
    for data in files:
        if len(data) > MAX_BYTES:
            raise ImageError("A photo is over 5 MB. Try a smaller one.")
        media_type = sniff(data)
        if media_type is None:
            raise ImageError("A photo must be a JPEG, PNG or WebP image.")
        images.append(Image(media_type, data))
    return images
