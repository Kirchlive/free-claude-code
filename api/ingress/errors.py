"""Domain errors for proxy auth and registry resolution (pre-transport mapping).

They are converted to JSON in
:class:`api.ingress.handlers.register_ingress_exception_handlers`.
"""

from __future__ import annotations


class IngressDetailError(Exception):
    """Ingress failure rendered as FastAPI-compatible ``{"detail": str}``."""

    status_code: int
    detail: str

    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ProviderResolutionAuthFailure(IngressDetailError):
    """Upstream credential missing or unusable while resolving a provider instance."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, 503)


class GatewayMissingProxyApiKey(IngressDetailError):
    """``ANTHROPIC_AUTH_TOKEN`` is set but the client sent no key."""

    def __init__(self) -> None:
        super().__init__("Missing API key", 401)


class GatewayInvalidProxyApiKey(IngressDetailError):
    """Client key does not match ``ANTHROPIC_AUTH_TOKEN``."""

    def __init__(self) -> None:
        super().__init__("Invalid API key", 401)


__all__ = [
    "GatewayInvalidProxyApiKey",
    "GatewayMissingProxyApiKey",
    "IngressDetailError",
    "ProviderResolutionAuthFailure",
]
