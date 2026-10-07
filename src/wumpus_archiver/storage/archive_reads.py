"""Archive reads: the named reads of the archive, each over a scope.

See ``docs/adr/0002`` and ``docs/adr/0003``. Every read takes the ``AsyncSession`` its
caller opened and never writes, commits, flushes or closes it. This module imports the
models only, never FastAPI or the API schemas.
"""

from enum import Enum


class MediaKind(Enum):
    """A kind of attachment the portal and the downloader select by content type."""

    IMAGE = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/avif")
    GIF = ("image/gif",)
    VIDEO = ("video/mp4", "video/webm", "video/quicktime")

    @property
    def content_types(self) -> tuple[str, ...]:
        """The content types an attachment of this kind may carry."""
        types: tuple[str, ...] = self.value
        return types


def escape_like(value: str, escape: str = "\\") -> str:
    """Escape SQL ``LIKE`` wildcards so user input matches literally.

    The escape character is escaped first, then ``%`` and ``_``. The caller must
    pass the same escape character to the ``LIKE`` clause (``ESCAPE '\\'`` in raw
    SQL or ``escape="\\\\"`` in SQLAlchemy ``like``/``ilike``).

    Args:
        value: Raw user-supplied search text
        escape: Escape character used by the ``LIKE`` clause

    Returns:
        The value with ``escape``, ``%`` and ``_`` each prefixed by ``escape``
    """
    return (
        value.replace(escape, escape + escape)
        .replace("%", escape + "%")
        .replace("_", escape + "_")
    )
