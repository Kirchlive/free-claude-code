"""Stable import paths for ingress domain errors (implementation in :mod:`api.ingress`)."""

from __future__ import annotations

from api.ingress.errors import (
    GatewayInvalidProxyApiKey,
    GatewayMissingProxyApiKey,
    IngressDetailError,
    ProviderResolutionAuthFailure,
)

__all__ = [
    "GatewayInvalidProxyApiKey",
    "GatewayMissingProxyApiKey",
    "IngressDetailError",
    "ProviderResolutionAuthFailure",
]
