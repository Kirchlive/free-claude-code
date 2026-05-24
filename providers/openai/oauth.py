"""ChatGPT OAuth credential loading + refresh for the Codex Responses transport.

Reads the token store written by the local ``codex`` CLI (``~/.codex/auth.json``)
and refreshes it against the OpenAI OAuth endpoint when the access token expires.
No API key is involved; this reuses the user's ChatGPT subscription session.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from loguru import logger

from providers.exceptions import AuthenticationError

OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
# Public client id used by the codex CLI's ChatGPT OAuth flow.
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

_NOT_AUTHED = (
    "OpenAI (Codex) is not authenticated. Run `codex login` so that "
    "{path} exists with a ChatGPT session."
)


class CodexOAuth:
    """Load and refresh ChatGPT OAuth tokens from a codex ``auth.json`` file."""

    def __init__(self, credential_file: str) -> None:
        self._path = Path(credential_file).expanduser()
        self._access_token: str | None = None
        self._account_id: str | None = None
        self._refresh_token: str | None = None
        self._loaded = False

    def _load(self) -> None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise AuthenticationError(_NOT_AUTHED.format(path=self._path)) from exc
        except OSError as exc:
            raise AuthenticationError(
                f"OpenAI (Codex) credentials at {self._path} could not be read. "
                "Run `codex login`."
            ) from exc

        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise AuthenticationError(
                f"OpenAI (Codex) credentials at {self._path} are not valid JSON. "
                "Run `codex login`."
            ) from exc

        tokens = data.get("tokens") if isinstance(data, dict) else None
        if not isinstance(tokens, dict):
            raise AuthenticationError(_NOT_AUTHED.format(path=self._path))
        access = tokens.get("access_token")
        if not isinstance(access, str) or not access:
            raise AuthenticationError(_NOT_AUTHED.format(path=self._path))

        self._access_token = access
        account_id = tokens.get("account_id")
        self._account_id = account_id if isinstance(account_id, str) else None
        refresh_token = tokens.get("refresh_token")
        self._refresh_token = refresh_token if isinstance(refresh_token, str) else None
        self._loaded = True

    def access_token(self) -> str:
        """Return the current access token, loading the file on first use."""
        if not self._loaded:
            self._load()
        assert self._access_token is not None
        return self._access_token

    def account_id(self) -> str | None:
        """Return the ChatGPT account id, if present."""
        if not self._loaded:
            self._load()
        return self._account_id

    async def refresh(self, client: httpx.AsyncClient) -> str:
        """Exchange the refresh token for a new access token and persist it."""
        if not self._loaded:
            self._load()
        if not self._refresh_token:
            raise AuthenticationError(
                "OpenAI (Codex) access token expired and no refresh token is "
                "available. Run `codex login`."
            )

        response = await client.post(
            OAUTH_TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": OAUTH_CLIENT_ID,
            },
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        new_access = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(new_access, str) or not new_access:
            raise AuthenticationError(
                "OpenAI (Codex) token refresh did not return an access token."
            )

        self._access_token = new_access
        new_refresh = payload.get("refresh_token")
        if isinstance(new_refresh, str) and new_refresh:
            self._refresh_token = new_refresh
        self._persist()
        return new_access

    def _persist(self) -> None:
        """Best-effort atomic write of the refreshed token back to auth.json."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("tokens"), dict):
                return
            data["tokens"]["access_token"] = self._access_token
            if self._refresh_token:
                data["tokens"]["refresh_token"] = self._refresh_token
            data["last_refresh"] = datetime.now(UTC).isoformat()

            fd, tmp_name = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=".auth.", suffix=".tmp.json"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle)
                os.replace(tmp_name, self._path)
            except BaseException:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
                raise
        except Exception as exc:
            # Token still usable in-memory for this process; persistence is best effort.
            logger.warning(
                "OpenAI (Codex) refreshed token persist failed: exc_type={}",
                type(exc).__name__,
            )
