"""Catalog-driven provider factory registrations for :mod:`providers.registry`."""

from collections.abc import Callable
from functools import partial

from config.provider_catalog import PROVIDER_CATALOG, SUPPORTED_PROVIDER_IDS
from config.settings import Settings
from providers.base import BaseProvider, ProviderConfig

ProviderFactory = Callable[[ProviderConfig, Settings], BaseProvider]


def _create_nvidia_nim(config: ProviderConfig, settings: Settings) -> BaseProvider:
    from providers.nvidia_nim import NvidiaNimProvider

    return NvidiaNimProvider(config, nim_settings=settings.nim)


def _create_open_router(config: ProviderConfig, _settings: Settings) -> BaseProvider:
    from providers.open_router import OpenRouterProvider

    return OpenRouterProvider(config)


def _create_deepseek(config: ProviderConfig, _settings: Settings) -> BaseProvider:
    from providers.deepseek import DeepSeekProvider

    return DeepSeekProvider(config)


def _instantiate_catalog_thin_native_messages(
    provider_id: str, config: ProviderConfig, _settings: Settings
) -> BaseProvider:
    """Build thin catalog shells (LM Studio, llama.cpp) sharing one implementation."""
    from providers.llamacpp import LlamaCppProvider
    from providers.lmstudio import LMStudioProvider

    if provider_id == "lmstudio":
        return LMStudioProvider(config)
    if provider_id == "llamacpp":
        return LlamaCppProvider(config)
    msg = f"unsupported thin native catalog id: {provider_id!r}"
    raise AssertionError(msg)


def _create_lmstudio(config: ProviderConfig, settings: Settings) -> BaseProvider:
    return _instantiate_catalog_thin_native_messages("lmstudio", config, settings)


def _create_llamacpp(config: ProviderConfig, settings: Settings) -> BaseProvider:
    return _instantiate_catalog_thin_native_messages("llamacpp", config, settings)


def _create_ollama(config: ProviderConfig, _settings: Settings) -> BaseProvider:
    from providers.ollama import OllamaProvider

    return OllamaProvider(config)


def _create_wafer(config: ProviderConfig, _settings: Settings) -> BaseProvider:
    from providers.wafer import WaferProvider

    return WaferProvider(config)


_CatalogOpenAiInner = Callable[[ProviderConfig, Settings], BaseProvider]


def _openai_chat_opencode_go(
    config: ProviderConfig, _settings: Settings
) -> BaseProvider:
    from providers.opencode import OpenCodeProvider

    return OpenCodeProvider(config, provider_name="OPENCODE_GO")


def _openai_chat_opencode(config: ProviderConfig, _settings: Settings) -> BaseProvider:
    from providers.opencode import OpenCodeProvider

    return OpenCodeProvider(config)


def _openai_chat_kimi(config: ProviderConfig, _settings: Settings) -> BaseProvider:
    from providers.kimi import KimiProvider

    return KimiProvider(config)


def _openai_chat_fireworks(config: ProviderConfig, _settings: Settings) -> BaseProvider:
    from providers.fireworks import FireworksProvider

    return FireworksProvider(config)


def _openai_chat_zai(config: ProviderConfig, _settings: Settings) -> BaseProvider:
    from providers.zai import ZaiProvider

    return ZaiProvider(config)


def _catalog_openai_chat_fallback(
    provider_id: str, config: ProviderConfig
) -> BaseProvider:
    from providers.openai_chat_adapter import CatalogOpenAIChatProvider

    return CatalogOpenAIChatProvider(provider_id, config)


_CATALOG_OPENAI_CHAT_BY_ID: dict[str, _CatalogOpenAiInner] = {
    "opencode_go": _openai_chat_opencode_go,
    "opencode": _openai_chat_opencode,
    "kimi": _openai_chat_kimi,
    "fireworks": _openai_chat_fireworks,
    "zai": _openai_chat_zai,
}


def _instantiate_catalog_openai_chat(
    provider_id: str, config: ProviderConfig, settings: Settings
) -> BaseProvider:
    """Construct catalog-backed OpenAI chat providers (see ``openai_request_module``)."""
    maker = _CATALOG_OPENAI_CHAT_BY_ID.get(provider_id)
    if maker is not None:
        return maker(config, settings)
    return _catalog_openai_chat_fallback(provider_id, config)


def _create_catalog_openai_chat(
    _config: ProviderConfig, _settings: Settings
) -> BaseProvider:
    """Catalog marker; per-id factories use :func:`_instantiate_catalog_openai_chat`."""
    raise AssertionError(
        "OpenAI catalog providers must bind via functools.partial(_instantiate_catalog_openai_chat, pid)"
    )


_MOD = globals()
PROVIDER_FACTORIES: dict[str, ProviderFactory] = {}
for pid, desc in PROVIDER_CATALOG.items():
    if desc.openai_request_module is not None:
        if desc.transport_type != "openai_chat":
            raise AssertionError(
                f"provider {pid!r}: openai_request_module requires transport_type "
                f"'openai_chat', got {desc.transport_type!r}"
            )
        PROVIDER_FACTORIES[pid] = partial(_instantiate_catalog_openai_chat, pid)
        continue
    try:
        factory_fn = _MOD[desc.registry_factory]
    except KeyError as exc:
        raise AssertionError(
            f"registry_factory {desc.registry_factory!r} missing from "
            f"providers.registry_factories "
            f"for provider {pid}"
        ) from exc
    if not callable(factory_fn):
        raise AssertionError(
            f"registry_factory {desc.registry_factory!r} for {pid} is not callable"
        )
    PROVIDER_FACTORIES[pid] = factory_fn

if set(PROVIDER_FACTORIES) != set(SUPPORTED_PROVIDER_IDS):
    raise AssertionError(
        "PROVIDER_FACTORIES and SUPPORTED_PROVIDER_IDS are out of sync: "
        f"factories={set(PROVIDER_FACTORIES)!r} "
        f"ids={set(SUPPORTED_PROVIDER_IDS)!r}"
    )
