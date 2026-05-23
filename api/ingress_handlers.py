"""Stable import paths for ingress exception handlers (implementation in :mod:`api.ingress`)."""

from __future__ import annotations

from api.ingress.handlers import register_ingress_exception_handlers

__all__ = ["register_ingress_exception_handlers"]
