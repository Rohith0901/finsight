"""Runtime configuration, read once from environment variables.

Every setting has a safe default except the API token, which must be set:
a server that accepts unauthenticated requests should never start by accident.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

LLM_PROVIDERS = ("none", "ollama", "gemini")


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    api_token: str
    shared_dir: Path = field(default=_REPO_ROOT / "shared")
    models_dir: Path = field(default=_REPO_ROOT / "backend" / "models")
    classifier_version: str = "v1"
    # Default assistant provider: "none" (templates only), "ollama" (local) or "gemini" (cloud).
    llm_provider: str = "ollama"
    ollama_enabled: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    llm_timeout_s: float = 30.0
    max_body_bytes: int = 5 * 1024 * 1024
    max_transactions: int = 5000

    @property
    def enabled_llm_providers(self) -> list[str]:
        providers = ["none"]
        if self.ollama_enabled:
            providers.append("ollama")
        if self.gemini_api_key:
            providers.append("gemini")
        return providers

    @property
    def default_llm_provider(self) -> str:
        wanted = self.llm_provider if self.llm_provider in LLM_PROVIDERS else "none"
        return wanted if wanted in self.enabled_llm_providers else "none"


def load_settings() -> Settings:
    token = os.environ.get("FINSIGHT_API_TOKEN", "").strip()
    if len(token) < 16:
        raise RuntimeError(
            "FINSIGHT_API_TOKEN must be set to a random string of at least 16 characters "
            "(run scripts/new_token.sh to make one)."
        )
    return Settings(
        api_token=token,
        shared_dir=_env_path("FINSIGHT_SHARED_DIR", _REPO_ROOT / "shared"),
        models_dir=_env_path("FINSIGHT_MODELS_DIR", _REPO_ROOT / "backend" / "models"),
        classifier_version=os.environ.get("FINSIGHT_CLASSIFIER_VERSION", "v1"),
        llm_provider=os.environ.get("FINSIGHT_LLM_PROVIDER", "ollama").strip().lower(),
        ollama_enabled=_env_bool("FINSIGHT_OLLAMA_ENABLED", True),
        ollama_url=os.environ.get("FINSIGHT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.environ.get("FINSIGHT_OLLAMA_MODEL", "qwen2.5:3b"),
        gemini_api_key=os.environ.get("FINSIGHT_GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("FINSIGHT_GEMINI_MODEL", "gemini-3.5-flash-lite"),
        llm_timeout_s=float(os.environ.get("FINSIGHT_LLM_TIMEOUT_S", "30")),
    )
