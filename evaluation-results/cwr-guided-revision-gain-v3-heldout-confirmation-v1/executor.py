"""Deliberately closed execution seam for the v3 heldout confirmation."""
from __future__ import annotations


class ExecutionBlocked(RuntimeError):
    """Raised until a reviewed native executor binds disclosure, route, and receipts."""


def dispatch_native(*_args: object, **_kwargs: object) -> None:
    raise ExecutionBlocked(
        "v3 heldout confirmation is provider-free: native dispatch requires a separately reviewed "
        "disclosure, route, prepared-record, and native-receipt executor"
    )
