"""Read-only catalog projection for XRefKit repositories."""

from .catalog import XRefCatalog
from .client_cache import DocumentCacheProtocolError, XidDocumentCache
from .context_registry import PromptContextAssembler, SessionXidContextRegistry

__version__ = "0.1.5"

__all__ = [
    "DocumentCacheProtocolError",
    "PromptContextAssembler",
    "SessionXidContextRegistry",
    "XRefCatalog",
    "XidDocumentCache",
    "__version__",
]
