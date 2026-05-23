"""Centralized configuration using Pydantic Settings."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .admin_optimization_settings import AdminOptimizationSettings
from .bot_settings import BotSettings
from .messaging_settings import MessagingSettings
from .model_routing_settings import ModelRoutingSettings
from .observability_settings import ObservabilitySettings
from .paths import default_claude_workspace_path
from .server_runtime_settings import ProviderThroughputSettings, ServerRuntimeSettings
from .settings_bundles import (
    build_admin_optimization_bundle,
    build_bot_bundle,
    build_messaging_bundle,
    build_model_routing_bundle,
    build_observability_bundle,
    build_provider_throughput_bundle,
    build_server_runtime_bundle,
    build_web_fetch_bundle,
)
from .settings_coherence_mixins import SettingsCoherenceValidatorsMixin
from .settings_credentials import ProviderCredentialsMixin
from .settings_env import (
    env_files_list,
)
from .settings_http import HttpAndThroughputMixin
from .settings_local_providers import LocalProviderEndpointsMixin
from .settings_messaging import MessagingAndBotsMixin
from .settings_model_routing import ModelRoutingMixin
from .settings_nim_chat import NimChatMixin
from .settings_observability import ObservabilityMixin
from .settings_optimizations import RequestOptimizationsMixin
from .settings_proxies import ProviderProxyMixin
from .settings_server import ServerBindMixin
from .settings_validators import (
    parse_empty_str_optional,
    reset_empty_log_cap_optional,
    validate_gateway_model_prefixed,
    validate_messaging_platform_value,
    validate_ollama_base_url_value,
    validate_positive_messaging_rate_limit,
    validate_positive_messaging_rate_window,
    validate_whisper_device_value,
)
from .settings_voice import VoiceNoteMixin
from .settings_web_tools import WebServerToolsMixin
from .web_fetch_settings import WebFetchSettings, normalize_web_fetch_allowed_schemes


@dataclass(frozen=True, slots=True)
class ConfiguredChatModelRef:
    """A unique configured chat model reference and the env keys that set it."""

    model_ref: str
    provider_id: str
    model_id: str
    sources: tuple[str, ...]


class Settings(
    ProviderCredentialsMixin,
    LocalProviderEndpointsMixin,
    ProviderProxyMixin,
    ModelRoutingMixin,
    HttpAndThroughputMixin,
    RequestOptimizationsMixin,
    WebServerToolsMixin,
    ObservabilityMixin,
    NimChatMixin,
    VoiceNoteMixin,
    MessagingAndBotsMixin,
    ServerBindMixin,
    SettingsCoherenceValidatorsMixin,
    BaseSettings,
):
    """Application settings loaded from environment variables."""

    @field_validator(
        "telegram_bot_token",
        "allowed_telegram_user_id",
        "discord_bot_token",
        "allowed_discord_channels",
        "model_opus",
        "model_sonnet",
        "model_haiku",
        "enable_opus_thinking",
        "enable_sonnet_thinking",
        "enable_haiku_thinking",
        mode="before",
    )
    @classmethod
    def parse_optional_str(cls, v: Any) -> Any:
        return parse_empty_str_optional(v)

    @field_validator("max_message_log_entries_per_chat", mode="before")
    @classmethod
    def parse_optional_log_cap(cls, v: Any) -> Any:
        return reset_empty_log_cap_optional(v)

    @property
    def claude_workspace(self) -> str:
        """Return the fixed Claude data workspace path."""

        return str(default_claude_workspace_path())

    @property
    def claude_cli_bin(self) -> str:
        """Return the fixed Claude Code binary name."""

        return "claude"

    @field_validator("whisper_device")
    @classmethod
    def validate_whisper_device(cls, v: str) -> str:
        return validate_whisper_device_value(v)

    @field_validator("messaging_platform")
    @classmethod
    def validate_messaging_platform(cls, v: str) -> str:
        return validate_messaging_platform_value(v)

    @field_validator("messaging_rate_limit")
    @classmethod
    def validate_messaging_rate_limit(cls, v: int) -> int:
        return validate_positive_messaging_rate_limit(v)

    @field_validator("messaging_rate_window")
    @classmethod
    def validate_messaging_rate_window(cls, v: float) -> float:
        return validate_positive_messaging_rate_window(v)

    @field_validator("web_fetch_allowed_schemes")
    @classmethod
    def validate_web_fetch_allowed_schemes(cls, v: str) -> str:
        return normalize_web_fetch_allowed_schemes(v)

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, v: str) -> str:
        return validate_ollama_base_url_value(v)

    @field_validator("model", "model_opus", "model_sonnet", "model_haiku")
    @classmethod
    def validate_model_format(cls, v: str | None) -> str | None:
        return validate_gateway_model_prefixed(v)

    @property
    def provider_type(self) -> str:
        """Extract provider type from the default model string."""
        return Settings.parse_provider_type(self.model)

    @property
    def model_name(self) -> str:
        """Extract the actual model name from the default model string."""
        return Settings.parse_model_name(self.model)

    def resolve_model(self, claude_model_name: str) -> str:
        """Resolve a Claude model name to the configured provider/model string.

        Classifies the incoming Claude model (opus/sonnet/haiku) and
        returns the model-specific override if configured, otherwise the fallback MODEL.
        """
        name_lower = claude_model_name.lower()
        if "opus" in name_lower and self.model_opus is not None:
            return self.model_opus
        if "haiku" in name_lower and self.model_haiku is not None:
            return self.model_haiku
        if "sonnet" in name_lower and self.model_sonnet is not None:
            return self.model_sonnet
        return self.model

    def configured_chat_model_refs(self) -> tuple[ConfiguredChatModelRef, ...]:
        """Return unique configured chat provider/model refs with source env keys."""
        candidates = (
            ("MODEL", self.model),
            ("MODEL_OPUS", self.model_opus),
            ("MODEL_SONNET", self.model_sonnet),
            ("MODEL_HAIKU", self.model_haiku),
        )
        sources_by_ref: dict[str, list[str]] = {}
        for source, model_ref in candidates:
            if model_ref is None:
                continue
            sources_by_ref.setdefault(model_ref, []).append(source)

        return tuple(
            ConfiguredChatModelRef(
                model_ref=model_ref,
                provider_id=Settings.parse_provider_type(model_ref),
                model_id=Settings.parse_model_name(model_ref),
                sources=tuple(sources),
            )
            for model_ref, sources in sources_by_ref.items()
        )

    def resolve_thinking(self, claude_model_name: str) -> bool:
        """Resolve whether thinking is enabled for an incoming Claude model name."""
        name_lower = claude_model_name.lower()
        if "opus" in name_lower and self.enable_opus_thinking is not None:
            return self.enable_opus_thinking
        if "haiku" in name_lower and self.enable_haiku_thinking is not None:
            return self.enable_haiku_thinking
        if "sonnet" in name_lower and self.enable_sonnet_thinking is not None:
            return self.enable_sonnet_thinking
        return self.enable_model_thinking

    def web_fetch_allowed_scheme_set(self) -> frozenset[str]:
        """Return normalized schemes allowed for web_fetch."""
        return self.web_fetch_bundle.allowed_scheme_set()

    @property
    def web_fetch_bundle(self) -> WebFetchSettings:
        """Grouped web_fetch / web_search guard settings."""
        return build_web_fetch_bundle(self)

    @property
    def observability_bundle(self) -> ObservabilitySettings:
        """Bundled verbosity and debug logging flags."""
        return build_observability_bundle(self)

    @property
    def model_routing_bundle(self) -> ModelRoutingSettings:
        """Model tiers and thinking knobs grouped for dashboards and manifests."""
        return build_model_routing_bundle(self)

    @property
    def bot_bundle(self) -> BotSettings:
        """Bots, workspace guard rails, and voice-note configuration."""
        return build_bot_bundle(self)

    @property
    def admin_optimization_bundle(self) -> AdminOptimizationSettings:
        """Admin-visible proxy shortcuts unrelated to throughput rate limits."""
        return build_admin_optimization_bundle(self)

    @computed_field
    def messaging_bundle(self) -> MessagingSettings:
        """Messaging knobs grouped for injection into optional bot runtime."""
        return build_messaging_bundle(self)

    @computed_field
    def server_runtime_bundle(self) -> ServerRuntimeSettings:
        """Primary HTTP bind + auth subset."""
        return build_server_runtime_bundle(self)

    @computed_field
    def provider_throughput_bundle(self) -> ProviderThroughputSettings:
        """Values mirrored into each :class:`~providers.base.ProviderConfig` instance."""
        return build_provider_throughput_bundle(self)

    @staticmethod
    def parse_provider_type(model_string: str) -> str:
        """Extract provider type from any 'provider/model' string."""
        return model_string.split("/", 1)[0]

    @staticmethod
    def parse_model_name(model_string: str) -> str:
        """Extract model name from any 'provider/model' string."""
        return model_string.split("/", 1)[1]

    model_config = SettingsConfigDict(
        env_file=env_files_list(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def reload_settings() -> Settings:
    """Clear cached settings and return a fresh ``Settings()`` instance."""
    get_settings.cache_clear()
    return get_settings()
