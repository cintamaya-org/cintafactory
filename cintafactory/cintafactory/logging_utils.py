from __future__ import annotations

import atexit
import contextvars
import json
import logging
import logging.config
import os
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
import sys
from pathlib import Path
from queue import Queue
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union

from .url_safety import is_http_url


# ---------------------------------------------------------------------------
# Context management
# ---------------------------------------------------------------------------

_request_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "cintafactory_request_context", default={}
)

DEFAULT_LOG_DIR_NAME = "logs"
DEFAULT_LOG_FILE_NAME = "application.jsonl"
DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5
DEFAULT_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()
LISTENER_CONFIG_KEY = "_listener_configs"

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default



def get_request_context() -> Dict[str, Any]:
    """Return the current logging context."""
    return dict(_request_context.get())


def bind_request_context(**values: Any) -> None:
    """Merge values into the request context."""
    context = get_request_context()
    context.update({key: value for key, value in values.items() if value is not None})
    _request_context.set(context)


def clear_request_context() -> None:
    """Reset the request context."""
    _request_context.set({})


# ---------------------------------------------------------------------------
# Filters and formatters
# ---------------------------------------------------------------------------

SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "api_key", "access_token"}


class RequestContextFilter(logging.Filter):
    """Attach contextvar values to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_request_context().items():
            setattr(record, key, value)
        if not getattr(record, "request_id", None):
            setattr(record, "request_id", "-")
        return True


class SensitiveDataFilter(logging.Filter):
    """Mask values that look sensitive in log record dictionaries."""

    def filter(self, record: logging.LogRecord) -> bool:
        self._scrub_dict(record.__dict__)
        extra = getattr(record, "extra_data", None)
        if isinstance(extra, MutableMapping):
            record.extra_data = self._scrub_dict(extra)
        return True

    def _scrub_dict(self, data: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        for key, value in list(data.items()):
            if isinstance(value, MutableMapping):
                data[key] = self._scrub_dict(value)  # type: ignore[assignment]
                continue
            if isinstance(key, str) and any(secret in key.lower() for secret in SENSITIVE_KEYS):
                data[key] = "***"
                continue
            if isinstance(value, str) and any(secret in value.lower() for secret in SENSITIVE_KEYS):
                data[key] = "***"
        return data


class JSONFormatter(logging.Formatter):
    """Render log records as JSON lines."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03d"

    def format(self, record: logging.LogRecord) -> str:
        record_dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", None),
            "username": getattr(record, "username", None),
            "path": getattr(record, "path", None),
            "method": getattr(record, "method", None),
            "extra": getattr(record, "extra_data", None),
            "module": record.module,
            "line": record.lineno,
        }
        return json.dumps({key: value for key, value in record_dict.items() if value is not None})


class ColorFormatter(logging.Formatter):
    """Pretty console formatting with colour when supported."""

    COLOURS = {
        "DEBUG": "\033[37m",
        "INFO": "\033[36m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"

    def __init__(self, fmt: str, use_colour: bool = True) -> None:
        super().__init__(fmt)
        self.use_colour = use_colour and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if self.use_colour:
            colour = self.COLOURS.get(record.levelname)
            if colour:
                return f"{colour}{message}{self.RESET}"
        return message


# ---------------------------------------------------------------------------
# Handler registry & queue infrastructure
# ---------------------------------------------------------------------------

HANDLER_REGISTRY: Dict[str, logging.Handler] = {}
QUEUE_REGISTRY: Dict[str, Queue] = {}
QUEUE_LISTENERS: List[QueueListener] = []


class StructuredRotatingFileHandler(RotatingFileHandler):
    """Rotating file handler that registers itself for queue fan-out."""

    def __init__(
        self,
        filename: str,
        maxBytes: int = 10 * 1024 * 1024,
        backupCount: int = 5,
        handler_name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, maxBytes=maxBytes, backupCount=backupCount, **kwargs)
        if handler_name:
            HANDLER_REGISTRY[handler_name] = self


class StructuredStreamHandler(logging.StreamHandler):
    """Console handler that registers itself for queue fan-out."""

    def __init__(self, stream=None, handler_name: Optional[str] = None) -> None:
        super().__init__(stream)
        if handler_name:
            HANDLER_REGISTRY[handler_name] = self


class CriticalNotificationHandler(logging.Handler):
    """Send critical alerts to a webhook or fallback to stderr."""

    def __init__(self, level: int = logging.ERROR, webhook_url: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(level=level)
        self.webhook_url = webhook_url
        self.handler_name = kwargs.get("handler_name")
        if self.handler_name:
            HANDLER_REGISTRY[self.handler_name] = self

    def emit(self, record: logging.LogRecord) -> None:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
        }
        webhook_url = self.webhook_url or ""
        if not is_http_url(webhook_url):
            sys.stderr.write(json.dumps(payload) + "\n")
            return
        try:
            import urllib.request

            request = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2):
                pass
        except Exception:
            self.handleError(record)


class AsyncQueueHandler(QueueHandler):
    """Queue-backed handler to defer heavy IO to background listeners."""

    def __init__(self, queue_name: str = "default") -> None:
        queue = QUEUE_REGISTRY.setdefault(queue_name, Queue(-1))
        super().__init__(queue)
        self.queue_name = queue_name


def _stop_queue_listeners() -> None:
    for listener in QUEUE_LISTENERS:
        try:
            listener.stop()
        except Exception:
            continue
    QUEUE_LISTENERS.clear()


def start_queue_listeners(configs: Sequence[Mapping[str, Any]]) -> None:
    _stop_queue_listeners()
    for config in configs:
        queue_name = config.get("queue_name", "default")
        handler_names: Iterable[str] = config.get("handlers", [])
        queue = QUEUE_REGISTRY.get(queue_name)
        if not queue:
            continue
        targets = [
            HANDLER_REGISTRY[name]
            for name in handler_names
            if name in HANDLER_REGISTRY and not isinstance(HANDLER_REGISTRY[name], AsyncQueueHandler)
        ]
        if not targets:
            continue
        listener = QueueListener(queue, *targets, respect_handler_level=True)
        listener.start()
        QUEUE_LISTENERS.append(listener)
    if QUEUE_LISTENERS:
        atexit.register(_stop_queue_listeners)


# ---------------------------------------------------------------------------
# Helper API for developers
# ---------------------------------------------------------------------------

class StructuredLoggerAdapter(logging.LoggerAdapter):
    """Ensure structured payloads travel consistently through loggers."""

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> Tuple[str, MutableMapping[str, Any]]:
        extra = kwargs.setdefault("extra", {})
        payload = extra.setdefault("extra_data", {})
        if isinstance(payload, MutableMapping):
            payload.update(self.extra)
        else:
            extra["extra_data"] = {**self.extra}
        fields = kwargs.pop("fields", None)
        if isinstance(fields, Mapping):
            extra["extra_data"].update(fields)
        return msg, kwargs


def get_logger(name: str = "cintafactory") -> StructuredLoggerAdapter:
    
    base_logger = logging.getLogger(name)
   
    return StructuredLoggerAdapter(base_logger, {})


def log_debug(message: str, **fields: Any) -> None:
    get_logger().debug(message, fields=fields)


def log_info(message: str, **fields: Any) -> None:
    get_logger().info(message, fields=fields)


def log_warning(message: str, **fields: Any) -> None:
    get_logger().warning(message, fields=fields)


def log_error(message: str, **fields: Any) -> None:
    get_logger().error(message, fields=fields)


def log_exception(message: str, **fields: Any) -> None:
    get_logger().exception(message, fields=fields)


# ---------------------------------------------------------------------------
# Logging configuration assembly
# ---------------------------------------------------------------------------

def build_logging_dict(base_dir: Path) -> Dict[str, Any]:
    """Construct the LOGGING dictConfig payload with listener wiring metadata."""

    log_dir_override = os.getenv("DJANGO_LOG_DIR")
    log_dir = Path(log_dir_override) if log_dir_override else base_dir.parent / DEFAULT_LOG_DIR_NAME
    log_file = log_dir / DEFAULT_LOG_FILE_NAME
    max_bytes = _env_int("DJANGO_LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES)
    backup_count = _env_int("DJANGO_LOG_BACKUP_COUNT", DEFAULT_LOG_BACKUP_COUNT)
    log_level = os.getenv("DJANGO_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    # Print structured logs to stdout by default; opt-out with DJANGO_LOG_TO_STDOUT=0.
    log_to_stdout = _env_flag("DJANGO_LOG_TO_STDOUT", True)
    filters = {
        "request_context": {"()": "cintafactory.logging_utils.RequestContextFilter"},
        "sensitive_data": {"()": "cintafactory.logging_utils.SensitiveDataFilter"},
    }

    formatters = {
        "json": {"()": "cintafactory.logging_utils.JSONFormatter"},
        "color": {
            "()": "cintafactory.logging_utils.ColorFormatter",
            "fmt": "%(asctime)s | %(levelname)s | %(request_id)s | %(name)s | %(message)s",
        },
    }

    handlers: Dict[str, Dict[str, Any]] = {
        "queue": {
            "class": "cintafactory.logging_utils.AsyncQueueHandler",
            "level": "DEBUG",
            "filters": ["request_context", "sensitive_data"],
        },
        "console": {
            "class": "cintafactory.logging_utils.StructuredStreamHandler",
            "level": log_level,
            "formatter": "color",
            "filters": ["request_context", "sensitive_data"],
            "stream": "ext://sys.stdout",
            "handler_name": "console",
        },
        "critical": {
            "class": "cintafactory.logging_utils.CriticalNotificationHandler",
            "level": "ERROR",
            "handler_name": "critical",
            "webhook_url": os.getenv("LOG_CRITICAL_WEBHOOK"),
        },
    }

    if log_to_stdout:
        handlers["json_file"] = {
            "class": "cintafactory.logging_utils.StructuredStreamHandler",
            "level": "DEBUG",
            "formatter": "json",
            "filters": ["request_context", "sensitive_data"],
            "stream": "ext://sys.stderr",
            "handler_name": "json_file",
        }
    else:
        handlers["json_file"] = {
            "class": "cintafactory.logging_utils.StructuredRotatingFileHandler",
            "level": "DEBUG",
            "formatter": "json",
            "filters": ["request_context", "sensitive_data"],
            "filename": str(log_file),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "handler_name": "json_file",
        }

    listener_configs: List[Dict[str, Any]] = [
        {"queue_name": "default", "handlers": ["console", "critical", "json_file"]},
    ]

    logging_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": filters,
        "formatters": formatters,
        "handlers": handlers,
        "root": {
            "level": log_level,
            "handlers": ["queue"],
        },
        "loggers": {
            "django.request": {"level": "INFO", "propagate": False, "handlers": ["queue"]},
            "django.security": {"level": "INFO", "propagate": False, "handlers": ["queue"]},
        },
    }

    logging_config[LISTENER_CONFIG_KEY] = listener_configs
    return logging_config


def configure_logging(config: Union[Path, Mapping[str, Any]]) -> Dict[str, Any]:
    """Apply logging configuration and wire up queue listeners."""

    if isinstance(config, Path):
        logging_config = build_logging_dict(config)
    else:
        logging_config = dict(config)

    listener_configs = logging_config.pop(LISTENER_CONFIG_KEY, None)
    logging.config.dictConfig(logging_config)
    if listener_configs:
        start_queue_listeners(listener_configs)
    return logging_config


__all__ = [
    "bind_request_context",
    "build_logging_dict",
    "clear_request_context",
    "configure_logging",
    "get_logger",
    "log_debug",
    "log_error",
    "log_exception",
    "log_info",
    "log_warning",
    "start_queue_listeners",
]
