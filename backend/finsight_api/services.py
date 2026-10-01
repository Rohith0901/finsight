"""Long-lived objects built once at startup: settings, the model and the assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Settings
from .llm.assistant import Assistant
from .llm.base import Provider
from .llm.gemini import GeminiProvider
from .llm.ollama import OllamaProvider
from .ml.classifier import JsonClassifier

log = logging.getLogger("finsight")


@dataclass
class Services:
    settings: Settings
    classifier: JsonClassifier | None
    assistant: Assistant


def build_providers(settings: Settings) -> dict[str, Provider]:
    providers: dict[str, Provider] = {}
    if settings.ollama_enabled:
        providers["ollama"] = OllamaProvider(settings.ollama_url, settings.ollama_model,
                                             settings.llm_timeout_s)
    if settings.gemini_api_key:
        providers["gemini"] = GeminiProvider(settings.gemini_api_key, settings.gemini_model,
                                             settings.llm_timeout_s)
    return providers


def load_classifier(settings: Settings) -> JsonClassifier | None:
    path = settings.models_dir / "classifier" / settings.classifier_version / "model.json"
    if not path.exists():
        log.warning("no classifier at %s; /v1/classify will answer 503", path)
        return None
    clf = JsonClassifier.load(path)
    log.info("loaded classifier %s (%d classes)", clf.version, len(clf.classes))
    return clf


def build_services(settings: Settings, providers: dict[str, Provider] | None = None) -> Services:
    providers = build_providers(settings) if providers is None else providers
    return Services(
        settings=settings,
        classifier=load_classifier(settings),
        assistant=Assistant(providers, settings.default_llm_provider),
    )
