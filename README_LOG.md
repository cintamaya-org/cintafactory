# Logging Quick Guide

This project ships with a structured logging helper (`cintafactory.logging_utils`) that keeps the log format consistent in both stdout and `logs/application.jsonl`. Use the helpers below whenever you add new log statements.

## 1. Pick a helper

For most cases you can call the shortcut functions that already use the shared project logger:

```python
from cintafactory.logging_utils import log_debug, log_info, log_warning, log_error, log_exception
```

They accept a message plus arbitrary keyword arguments that become structured JSON fields:

```python
log_info("Order confirmed", order_id=order.id, amount=order.total)
log_warning("Payment gateway slow", gateway="stripe", duration_ms=elapsed_ms)

try:
    service.sync()
except ServiceError:
    log_exception("Failed to sync partner catalog", partner_id=partner.id)
```

Need module-level control (custom logger name, extra adapters, etc.)? Grab a logger directly:

```python
from cintafactory.logging_utils import get_logger

logger = get_logger(__name__)
logger.info("Provisioning VM", fields={"vm_id": vm.id, "region": vm.region})
```

## 2. Attach request context (optional but recommended in views/tasks)

`bind_request_context` stores metadata (request id, user, etc.) so every subsequent log automatically includes it. Remember to clear the context when you are done (middleware already does this for regular HTTP requests).

```python
from cintafactory.logging_utils import bind_request_context, clear_request_context, log_info

def sync_order(request, order_id: str):
    bind_request_context(request_id=request.request_id, user_id=request.user.id)
    try:
        order = sync_service.sync(order_id)
        log_info("Sync completed", order_id=order.id, status=order.status)
    finally:
        clear_request_context()
```

## 3. Choose the right level

- `log_debug` – noisy internals, disabled in production by default.
- `log_info` – lifecycle events users might care about (create/update/delete, background job completion, etc.).
- `log_warning` – recoverable issues or retries.
- `log_error` – failures that degrade functionality.
- `log_exception` – like `log_error` but automatically includes the traceback; use inside `except` blocks.

## 4. Where the logs end up

In development `docker compose logs web` shows the colourised console handler, while structured lines go to `cintafactory/logs/application.jsonl`. In containerised environments you can set `DJANGO_LOG_TO_STDOUT=1` (or rely on `RUNNING_IN_DOCKER=1`) to send JSON straight to stdout instead of the rotating file.

Following these patterns keeps our log streams searchable and makes alerts, dashboards, and support workflows much easier.
