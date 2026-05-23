"""Cross-cutting ``Settings`` :class:`~pydantic.model_validator` hooks.

Kept separate from ``settings.py`` so the hub stays composition + facade fields only.
"""

import os
from typing import Any, cast

from pydantic import model_validator

from .settings_env import dotenv_last_value_for_key, removed_env_var_migration_error


class SettingsCoherenceValidatorsMixin:
    """Validators that span multiple mixin-owned fields (merged into ``Settings``)."""

    @model_validator(mode="before")
    @classmethod
    def reject_removed_env_vars(cls, data: Any) -> Any:
        """Fail fast when removed environment variables are still configured."""
        model_config = cast(Any, cls).model_config
        if message := removed_env_var_migration_error(model_config):
            raise ValueError(message)
        return data

    @model_validator(mode="after")
    def check_nvidia_nim_api_key(self: Any) -> Any:
        if (
            self.voice_note_enabled
            and self.whisper_device == "nvidia_nim"
            and not self.nvidia_nim_api_key.strip()
        ):
            raise ValueError(
                "NVIDIA_NIM_API_KEY is required when WHISPER_DEVICE is 'nvidia_nim'. "
                "Set it in your .env file."
            )
        return self

    @model_validator(mode="after")
    def prefer_dotenv_anthropic_auth_token(self: Any) -> Any:
        """Let explicit .env auth config override stale shell/client tokens."""
        dotenv_value = dotenv_last_value_for_key(
            self.model_config, "ANTHROPIC_AUTH_TOKEN"
        )
        if dotenv_value is not None:
            self.anthropic_auth_token = dotenv_value
        return self

    def uses_process_anthropic_auth_token(self: Any) -> bool:
        """Return whether proxy auth came from process env, not dotenv config."""
        if (
            dotenv_last_value_for_key(self.model_config, "ANTHROPIC_AUTH_TOKEN")
            is not None
        ):
            return False
        return bool(os.environ.get("ANTHROPIC_AUTH_TOKEN"))
