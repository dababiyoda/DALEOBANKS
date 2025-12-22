"""Request observability: structured logging hooks and Prometheus metrics."""
from typing import Optional
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

request_counter = Counter(
    "app_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status", "role"],
)

request_latency = Histogram(
    "app_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path", "role"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

external_call_outcomes = Counter(
    "app_external_call_outcomes_total",
    "External call outcomes",
    ["system", "result"],
)

metrics_router = APIRouter()


@metrics_router.get("/metrics")
async def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_request_metrics(request: Request, status_code: int, duration: float, role: str):
    path = request.url.path
    method = request.method
    role_label = role or "anonymous"
    request_counter.labels(method=method, path=path, status=str(status_code), role=role_label).inc()
    request_latency.labels(method=method, path=path, role=role_label).observe(duration)


def record_external_call(system: str, result: str):
    external_call_outcomes.labels(system=system, result=result).inc()


def request_timer() -> float:
    return time.perf_counter()


def elapsed(start_time: Optional[float]) -> float:
    if start_time is None:
        return 0.0
    return time.perf_counter() - start_time
