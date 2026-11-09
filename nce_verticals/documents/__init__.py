"""nce_verticals.documents — C14 Document Register module.

Phase A Wave A-4:
Provides the shared-core document register, polymorphic entity attachments,
and expiring share token capabilities.
"""

from __future__ import annotations

from nce_verticals.documents.models import (
    DocumentLinkRecord,
    DocumentRecord,
    DocumentShareRecord,
)
from nce_verticals.documents.resources import DOCUMENT_SPEC
from nce_verticals.documents.service import (
    archive_document,
    create_document_share,
    get_document,
    get_document_share,
    is_share_active,
    link_document,
    list_entity_documents,
    register_document,
    revoke_document_share,
    unlink_document,
)

__all__ = [
    "DOCUMENT_SPEC",
    "DocumentRecord",
    "DocumentLinkRecord",
    "DocumentShareRecord",
    "register_document",
    "get_document",
    "archive_document",
    "link_document",
    "unlink_document",
    "list_entity_documents",
    "create_document_share",
    "get_document_share",
    "revoke_document_share",
    "is_share_active",
]
