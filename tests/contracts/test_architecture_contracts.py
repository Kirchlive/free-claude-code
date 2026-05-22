from __future__ import annotations

import re
import tomllib
from pathlib import Path

from config.provider_catalog import (
    PROVIDER_CATALOG,
    SUPPORTED_PROVIDER_IDS,
    provider_ids_for_transport,
)
from providers.registry import PROVIDER_FACTORIES


def test_provider_catalog_every_descriptor_has_registry_factory() -> None:
    missing = sorted(
        pid for pid, desc in PROVIDER_CATALOG.items() if not desc.registry_factory
    )
    assert missing == []


def test_provider_factories_mirror_catalog_ids() -> None:
    catalog_ids = set(PROVIDER_CATALOG)
    factory_ids = set(PROVIDER_FACTORIES)
    assert catalog_ids == factory_ids == set(SUPPORTED_PROVIDER_IDS)


def test_provider_ids_for_transport_openai_matches_service_guard() -> None:
    """Server-tool branching must stay catalog-driven."""
    import api.services as services

    assert (
        provider_ids_for_transport("openai_chat") == services._OPENAI_CHAT_UPSTREAM_IDS
    )


def test_openai_transport_ids_are_nonempty_and_subset_of_supported() -> None:
    ids = provider_ids_for_transport("openai_chat")
    assert ids
    assert ids <= set(PROVIDER_CATALOG.keys())
    assert ids <= set(SUPPORTED_PROVIDER_IDS)


def test_smoke_lib_has_no_sse_shim_module() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    assert not (repo_root / "smoke" / "lib" / "sse.py").exists()


def test_api_package_exports() -> None:
    import api

    assert set(api.__all__) == {
        "MessagesRequest",
        "MessagesResponse",
        "TokenCountRequest",
        "TokenCountResponse",
        "create_app",
    }


def test_root_env_example_is_the_single_template_source() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    root_example = repo_root / ".env.example"
    duplicate_example = repo_root / "config" / "env.example"

    assert root_example.is_file()
    assert not duplicate_example.exists()


def test_root_env_example_is_packaged_for_fcc_init() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text("utf-8"))

    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]

    assert force_include[".env.example"] == "cli/env.example"


def test_pyproject_first_party_packages_match_packaged_roots() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"known-first-party = \[(?P<items>[^\]]+)\]", pyproject)

    assert match is not None
    configured = {
        item.strip().strip('"')
        for item in match.group("items").split(",")
        if item.strip()
    }
    expected = {"api", "cli", "config", "core", "messaging", "providers", "smoke"}
    assert configured == expected
