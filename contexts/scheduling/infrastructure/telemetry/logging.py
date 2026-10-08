"""Structured JSON logs via structlog over stdlib logging (SPEC §9).

Every line carries the request's correlation_id and route (bound by the middleware) and,
inside a traced request, trace_id/span_id. Application code logs with stdlib `logging`
and `extra={...}`; no PII beyond ids.
"""

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog
from opentelemetry import trace


def add_trace_context(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = format(context.trace_id, "032x")
        event_dict["span_id"] = format(context.span_id, "016x")
    return event_dict


_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    add_trace_context,
]


def _formatter(renderer: Any) -> logging.Formatter:
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
        foreign_pre_chain=[*_SHARED_PROCESSORS, structlog.stdlib.ExtraAdder()],
    )


def JsonFormatterFactory() -> logging.Formatter:  # noqa: N802 - logging dictConfig "()" factory
    return _formatter(structlog.processors.JSONRenderer())


def ConsoleFormatterFactory() -> logging.Formatter:  # noqa: N802
    return _formatter(structlog.dev.ConsoleRenderer())


def configure_structlog() -> None:
    structlog.configure(
        processors=[*_SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def logging_config(level: str, fmt: str) -> dict[str, Any]:
    """Django LOGGING dict: everything to stdout as JSON (or console in development)."""
    factory = "ConsoleFormatterFactory" if fmt == "console" else "JsonFormatterFactory"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"structured": {"()": f"{__name__}.{factory}"}},
        "handlers": {
            "stdout": {"class": "logging.StreamHandler", "formatter": "structured"},
        },
        "root": {"handlers": ["stdout"], "level": level},
        "loggers": {
            # 4xx are expected outcomes (validation, conflicts); keep them out of WARN noise.
            "django.request": {"level": "ERROR"},
            "django.server": {"level": "WARNING"},
        },
    }
