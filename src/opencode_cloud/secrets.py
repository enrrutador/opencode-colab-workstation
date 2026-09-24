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

    Kaggle exposes secrets via the `kagglehub` library or via environment
    variables injected by the Kaggle kernel. This implementation prefers
    the official `kaggle.secrets` interface when available.
    """

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        # Prefer Kaggle's native secrets module if available.
        try:
            from kaggle.secrets import SecretsClient  # type: ignore

            client = SecretsClient()
            try:
                return client.get_secret(key)
            except Exception:
                pass
        except Exception:
            pass

        # Fallback: environment variable (Kaggle also injects some secrets).
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