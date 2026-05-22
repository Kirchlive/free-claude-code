"""Managed env persistence, validation, and admin API helpers."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from io import StringIO
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import ValidationError

from config.paths import managed_env_path
from config.provider_catalog import PROVIDER_CATALOG
from config.settings import Settings

from .admin_manifest import (
    FIELD_BY_KEY,
    FIELDS,
    MASKED_SECRET,
    SECTIONS,
    ConfigFieldSpec,
    SourceType,
)


def repo_env_path() -> Path:
    """Return the repo-local env path."""

    return Path(".env")


def explicit_env_path() -> Path | None:
    """Return the explicit FCC_ENV_FILE path, when configured."""

    if explicit := os.environ.get("FCC_ENV_FILE"):
        return Path(explicit)
    return None


def configured_env_files() -> tuple[tuple[SourceType, Path], ...]:
    """Return dotenv files in low-to-high precedence order."""

    files: list[tuple[SourceType, Path]] = [
        ("repo_env", repo_env_path()),
        ("managed_env", managed_env_path()),
    ]
    if explicit := explicit_env_path():
        files.append(("explicit_env_file", explicit))
    return tuple(files)


def _template_text() -> str:
    import importlib.resources

    packaged = importlib.resources.files("cli").joinpath("env.example")
    if packaged.is_file():
        return packaged.read_text("utf-8")

    source_template = Path(__file__).resolve().parents[1] / ".env.example"
    if source_template.is_file():
        return source_template.read_text(encoding="utf-8")

    return ""


def _dotenv_values_from_text(text: str) -> dict[str, str]:
    values = dotenv_values(stream=StringIO(text))
    return {key: "" if value is None else value for key, value in values.items()}


def template_values() -> dict[str, str]:
    """Return .env.example values plus manifest defaults for newer fields."""

    values = _dotenv_values_from_text(_template_text())
    for field in FIELDS:
        values.setdefault(field.key, field.default)
    return values


def _dotenv_values_from_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = dotenv_values(path)
    return {key: "" if value is None else value for key, value in values.items()}


def _field_input_key(field: ConfigFieldSpec) -> str | None:
    if field.settings_attr is None:
        return None
    model_field = Settings.model_fields[field.settings_attr]
    alias = model_field.validation_alias
    if alias is None:
        return field.settings_attr
    return str(alias)


def _is_locked_source(source: SourceType) -> bool:
    return source in {"process", "explicit_env_file"}


def _normalize_for_env(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _display_value(field: ConfigFieldSpec, value: str) -> str:
    if field.secret and value:
        return MASKED_SECRET
    return value


def _load_value_state() -> dict[str, dict[str, Any]]:
    values = template_values()
    sources: dict[str, SourceType] = {
        key: "template" if key in values else "default" for key in FIELD_BY_KEY
    }

    for source, path in configured_env_files():
        file_values = _dotenv_values_from_file(path)
        for key, value in file_values.items():
            if key in FIELD_BY_KEY:
                values[key] = value
                sources[key] = source

    for key in FIELD_BY_KEY:
        if key in os.environ:
            values[key] = os.environ[key]
            sources[key] = "process"

    return {
        key: {
            "value": values.get(key, ""),
            "source": sources.get(key, "default"),
        }
        for key in FIELD_BY_KEY
    }


def load_config_response() -> dict[str, Any]:
    """Return manifest and current config values for the admin UI."""

    state = _load_value_state()
    fields: list[dict[str, Any]] = []
    for field in FIELDS:
        entry = state[field.key]
        source = entry["source"]
        raw_value = entry["value"]
        fields.append(
            {
                "key": field.key,
                "label": field.label,
                "section": field.section_id,
                "type": field.field_type,
                "value": _display_value(field, raw_value),
                "configured": bool(str(raw_value).strip()),
                "source": source,
                "locked": _is_locked_source(source),
                "secret": field.secret,
                "advanced": field.advanced,
                "restart_required": field.restart_required,
                "session_sensitive": field.session_sensitive,
                "options": list(field.options),
                "description": field.description,
            }
        )

    return {
        "sections": [
            {
                "id": section.section_id,
                "label": section.label,
                "description": section.description,
                "advanced": section.advanced,
            }
            for section in SECTIONS
        ],
        "fields": fields,
        "paths": {
            "managed": str(managed_env_path()),
            "repo": str(repo_env_path()),
            "explicit": str(explicit_env_path()) if explicit_env_path() else None,
        },
        "provider_status": provider_config_status(state),
    }


def _target_values_with_updates(updates: Mapping[str, Any]) -> dict[str, str]:
    state = _load_value_state()
    values = template_values()

    # Preserve existing managed values when present. If no managed config exists,
    # seed the first write from effective repo values to migrate legacy setups.
    managed_values = _dotenv_values_from_file(managed_env_path())
    if managed_values:
        values.update(
            {key: val for key, val in managed_values.items() if key in values}
        )
    else:
        for key, entry in state.items():
            if entry["source"] in {"repo_env", "template", "default"}:
                values[key] = str(entry["value"])

    for key, value in updates.items():
        field = FIELD_BY_KEY.get(key)
        if field is None:
            continue
        if _is_locked_source(state[key]["source"]):
            continue
        if field.secret and value == MASKED_SECRET:
            continue
        values[key] = _normalize_for_env(value)

    for field in FIELDS:
        values.setdefault(field.key, field.default)
    return values


def _effective_values_for_validation(
    target_values: Mapping[str, str],
) -> dict[str, str]:
    values = dict(target_values)
    for key, entry in _load_value_state().items():
        if _is_locked_source(entry["source"]):
            values[key] = str(entry["value"])
    return values


def validate_values(values: Mapping[str, str]) -> tuple[bool, list[str]]:
    """Validate proposed env values against the Settings model."""

    kwargs: dict[str, Any] = {"_env_file": None}
    for field in FIELDS:
        input_key = _field_input_key(field)
        if input_key is None:
            continue
        kwargs[input_key] = values.get(field.key, "")

    try:
        Settings(**kwargs)
    except ValidationError as exc:
        return False, _format_validation_errors(exc)
    return True, []


def _format_validation_errors(exc: ValidationError) -> list[str]:
    errors: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        message = str(error.get("msg", "Invalid value"))
        errors.append(f"{loc}: {message}" if loc else message)
    return errors


def validate_updates(updates: Mapping[str, Any]) -> dict[str, Any]:
    """Validate partial admin updates and return a masked generated env preview."""

    target_values = _target_values_with_updates(updates)
    effective_values = _effective_values_for_validation(target_values)
    valid, errors = validate_values(effective_values)
    return {
        "valid": valid,
        "errors": errors,
        "env_preview": render_env_file(target_values, mask_secrets=True),
    }


def changed_pending_fields(updates: Mapping[str, Any]) -> list[str]:
    """Return changed fields that require manual runtime action."""

    state = _load_value_state()
    pending: list[str] = []
    for key, value in updates.items():
        field = FIELD_BY_KEY.get(key)
        if field is None or not (field.restart_required or field.session_sensitive):
            continue
        if _normalize_for_env(value) == str(state[key]["value"]):
            continue
        pending.append(key)
    return pending


def write_managed_env(updates: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and atomically write the admin-managed env file."""

    validation = validate_updates(updates)
    if not validation["valid"]:
        return validation | {"applied": False, "pending_fields": []}

    target_values = _target_values_with_updates(updates)
    pending_fields = changed_pending_fields(updates)
    path = managed_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(render_env_file(target_values), encoding="utf-8")
    os.replace(temp_path, path)
    return {
        "applied": True,
        "valid": True,
        "errors": [],
        "env_preview": render_env_file(target_values, mask_secrets=True),
        "path": str(path),
        "pending_fields": pending_fields,
    }


def _quote_env_value(value: str) -> str:
    if value == "":
        return ""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    if any(char.isspace() for char in value) or any(
        char in value for char in ('"', "#", "=", "$")
    ):
        return f'"{escaped}"'
    return value


def render_env_file(values: Mapping[str, str], *, mask_secrets: bool = False) -> str:
    """Render a complete grouped env file."""

    lines: list[str] = [
        "# Managed by Free Claude Code /admin.",
        "# Edit in the server UI when possible.",
        "",
    ]
    fields_by_section: dict[str, list[ConfigFieldSpec]] = {
        section.section_id: [] for section in SECTIONS
    }
    for field in FIELDS:
        fields_by_section.setdefault(field.section_id, []).append(field)

    for section in SECTIONS:
        lines.append(f"# {section.label}")
        for field in fields_by_section.get(section.section_id, []):
            value = values.get(field.key, field.default)
            if mask_secrets and field.secret and value:
                value = MASKED_SECRET
            lines.append(f"{field.key}={_quote_env_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def provider_config_status(
    state: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return provider configuration status without making network calls."""

    state = state or _load_value_state()
    statuses: list[dict[str, Any]] = []
    for provider_id, descriptor in PROVIDER_CATALOG.items():
        if descriptor.credential_env is None:
            base_url = ""
            if descriptor.base_url_attr is not None:
                base_url = _value_for_settings_attr(state, descriptor.base_url_attr)
            statuses.append(
                {
                    "provider_id": provider_id,
                    "kind": "local",
                    "status": "missing_url" if not base_url.strip() else "unknown",
                    "label": "Missing URL" if not base_url.strip() else "Not checked",
                    "base_url": base_url or descriptor.default_base_url or "",
                }
            )
            continue

        value = str(state.get(descriptor.credential_env, {}).get("value", ""))
        configured = bool(value.strip())
        statuses.append(
            {
                "provider_id": provider_id,
                "kind": "remote",
                "status": "configured" if configured else "missing_key",
                "label": "Configured" if configured else "Missing key",
                "credential_env": descriptor.credential_env,
            }
        )
    return statuses


def _value_for_settings_attr(
    state: Mapping[str, Mapping[str, Any]], settings_attr: str
) -> str:
    for field in FIELDS:
        if field.settings_attr == settings_attr:
            return str(state.get(field.key, {}).get("value", field.default))
    return ""


def env_keys() -> frozenset[str]:
    """Return env keys owned by the admin manifest."""

    return frozenset(field.key for field in FIELDS)


def fields_with_attrs() -> Iterable[ConfigFieldSpec]:
    """Yield fields that validate through Settings."""

    return (field for field in FIELDS if field.settings_attr is not None)
