"""Secrets abstraction.

Secrets are retrieved from the platform's native secrets mechanism when
available (Kaggle Secrets), and fall back to environment variables.
Secrets are never written to disk in plain text, never logged, and never
included in shell command arguments.
"""

from __future__ import annotations

import os
from typing import Optional


class SecretsManager:
    """Abstract secrets provider.

    Subclasses implement platform-specific retrieval.
    """

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        raise NotImplementedError

    def get_required(self, key: str) -> str:
        val = self.get(key)
        if val is None:
            raise RuntimeError(f"Required secret '{key}' is not available.")
        return val


class EnvSecrets(SecretsManager):
    """Read secrets from environment variables only."""

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return os.environ.get(key, default)


class KaggleSecrets(SecretsManager):
    """Read secrets from Kaggle Secrets.

    Uses kaggle_secrets.UserSecretsClient which is the official Kaggle
    interface inside notebooks. Falls back to environment variables.
    """

    def __init__(self):
        self._client = None
        try:
            from kaggle_secrets import UserSecretsClient  # type: ignore

            self._client = UserSecretsClient()
        except Exception:
            self._client = None

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if self._client:
            try:
                return self._client.get_secret(key)
            except Exception:
                pass
        # Fallback: environment variable
        return os.environ.get(key, default)


def get_secrets_manager(runtime: Optional[str] = None) -> SecretsManager:
    """Return the appropriate SecretsManager for the given runtime."""
    if runtime is None:
        from .runtime import detect_runtime

        runtime = detect_runtime()
    if runtime == "kaggle":
        return KaggleSecrets()
    return EnvSecrets()


def load_secret(key: str, runtime: Optional[str] = None) -> Optional[str]:
    """Convenience function to load a single secret."""
    return get_secrets_manager(runtime).get(key)


def load_required_secret(key: str, runtime: Optional[str] = None) -> str:
    return get_secrets_manager(runtime).get_required(key)