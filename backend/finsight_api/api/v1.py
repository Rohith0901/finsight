"""The /v1 routes. Each request carries the data it needs; nothing is stored."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import API_VERSION
from ..engine.forecast import compute_forecast
from ..engine.safe_to_spend import compute_safe_to_spend
from ..engine.whatif import compute_what_if
from ..errors import APIError
from ..ml import anomaly, recurring
from ..schemas import (
    AnomaliesResponse,
    ChatRequest,
    ChatResponse,
    ClassifyRequest,
    ClassifyResponse,
    ForecastRequest,
    ForecastResponse,
    InsightsRequest,
    InsightsResponse,
    ModelInfo,
    RecurringResponse,
    SafeToSpendRequest,
    SafeToSpendResponse,
    WhatIfRequest,
    WhatIfResponse,
    Window,
)
from ..security import require_token
from ..services import Services

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


def services(request: Request) -> Services:
    return request.app.state.services


@router.post("/classify", response_model=ClassifyResponse)
def classify(req: ClassifyRequest, svc: Services = Depends(services)) -> ClassifyResponse:
    if svc.classifier is None:
        raise APIError(503, "model_unavailable",
                       "No classifier model is loaded. Run `make train` and restart.")
    return ClassifyResponse(
        model_version=svc.classifier.version,
        threshold=svc.classifier.threshold,
        items=svc.classifier.predict(req.items),
    )


@router.post("/recurring", response_model=RecurringResponse)
def detect_recurring(req: Window) -> RecurringResponse:
    return RecurringResponse(
        algorithm=recurring.ALGORITHM,
        items=recurring.detect_recurring(req.transactions, req.as_of),
    )


def _anomalies(req: Window, rec) -> AnomaliesResponse:
    exclude = frozenset(r.merchant_norm for r in rec)
    return AnomaliesResponse(
        algorithm=anomaly.ALGORITHM,
        threshold=anomaly.THRESHOLD,
        min_observations=anomaly.MIN_OBSERVATIONS,
        items=anomaly.detect_anomalies(req.transactions, req.as_of, exclude_merchants=exclude),
    )


@router.post("/anomalies", response_model=AnomaliesResponse)
def detect_anomalies(req: Window) -> AnomaliesResponse:
    return _anomalies(req, recurring.detect_recurring(req.transactions, req.as_of))


@router.post("/forecast", response_model=ForecastResponse)
def forecast(req: ForecastRequest) -> ForecastResponse:
    rec = req.recurring if req.recurring is not None else recurring.detect_recurring(
        req.transactions, req.as_of)
    return compute_forecast(req.transactions, req.as_of, rec)


@router.post("/safe-to-spend", response_model=SafeToSpendResponse)
def safe_to_spend(req: SafeToSpendRequest) -> SafeToSpendResponse:
    if req.recurring is not None:
        rec = req.recurring
    elif req.transactions:
        rec = recurring.detect_recurring(req.transactions, req.as_of)
    else:
        rec = []
    return compute_safe_to_spend(req.as_of, req.balance_paise, req.savings_target_paise, rec,
                                 req.transactions)


@router.post("/whatif", response_model=WhatIfResponse)
def what_if(req: WhatIfRequest) -> WhatIfResponse:
    rec = recurring.detect_recurring(req.transactions, req.as_of)
    return compute_what_if(req.transactions, req.as_of, rec, req.changes, req.balance_paise,
                           req.savings_target_paise)


@router.post("/insights", response_model=InsightsResponse)
def insights(req: InsightsRequest) -> InsightsResponse:
    """Recurring, anomalies, forecast and safe-to-spend from one upload of the window."""
    rec = recurring.detect_recurring(req.transactions, req.as_of)
    safe = None
    if req.balance_paise is not None:
        safe = compute_safe_to_spend(req.as_of, req.balance_paise, req.savings_target_paise, rec,
                                     req.transactions)
    return InsightsResponse(
        as_of=req.as_of,
        recurring=RecurringResponse(algorithm=recurring.ALGORITHM, items=rec),
        anomalies=_anomalies(req, rec),
        forecast=compute_forecast(req.transactions, req.as_of, rec),
        safe_to_spend=safe,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, svc: Services = Depends(services)) -> ChatResponse:
    return svc.assistant.answer(req)


@router.get("/model-info", response_model=ModelInfo)
def model_info(svc: Services = Depends(services)) -> ModelInfo:
    clf = svc.classifier
    return ModelInfo(
        api_version=API_VERSION,
        classifier={
            "loaded": clf is not None,
            "version": clf.version if clf else None,
            "dataset_version": clf.dataset_version if clf else None,
            "trained_at": clf.trained_at if clf else None,
            "classes": clf.classes if clf else [],
            "threshold": clf.threshold if clf else None,
            "metrics": clf.metrics if clf else {},
        },
        algorithms={
            "recurring": recurring.ALGORITHM,
            "anomalies": anomaly.ALGORITHM,
            "forecast": "backtest-select-v1",
        },
        llm={
            "default_provider": svc.settings.default_llm_provider,
            "enabled_providers": svc.settings.enabled_llm_providers,
        },
    )
