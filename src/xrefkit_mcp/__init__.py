"""Read-only catalog projection for XRefKit repositories."""

from .catalog import XRefCatalog
from .client_cache import DocumentCacheProtocolError, XidDocumentCache

__version__ = "0.1.5"

__all__ = [
    "DocumentCacheProtocolError",
    "XRefCatalog",
    "XidDocumentCache",
    "__version__",
]
