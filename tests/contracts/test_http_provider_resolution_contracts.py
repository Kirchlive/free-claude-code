from pathlib import Path


def test_live_api_handlers_do_not_call_process_cached_provider_helpers() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    watched = ("api/routes.py", "api/services.py")

    needles = (
        "get_process_cached_provider(",
        "get_process_cached_provider_for_type(",
    )
    for relative in watched:
        body = (repo_root / relative).read_text(encoding="utf-8")
        banned_hits = [token for token in needles if token in body]
        assert banned_hits == [], f"{relative} must avoid {banned_hits!r}"


_ALLOWED_PROCESS_CACHE_MODULES = frozenset(
    {
        "api/dependencies.py",
        "api/provider_process_cache.py",
    }
)
"""Modules that may reference PROCESS_PROVIDERS / provider_process_cache module name."""


def test_api_must_not_touch_process_providers_outside_allowlist() -> None:
    """Prevent bypassing resolve_provider/process-cache façade from random api modules."""
    repo_root = Path(__file__).resolve().parents[2]
    needles = ("provider_process_cache", "PROCESS_PROVIDERS")
    offenders: list[str] = []
    api_root = repo_root / "api"
    for path in sorted(api_root.rglob("*.py")):
        rel = path.relative_to(repo_root).as_posix()
        if rel in _ALLOWED_PROCESS_CACHE_MODULES:
            continue
        text = path.read_text(encoding="utf-8")
        hits = [n for n in needles if n in text]
        if hits:
            offenders.append(f"{rel}: contains {hits!r}")
    assert offenders == [], (
        "Touch process-level provider dict only via api.dependencies / "
        "api.provider_process_cache / api/__init__.\n" + "\n".join(offenders)
    )
