"""Sentry error-reporting helpers for the Nudge desktop client.

All public functions are safe no-ops when no DSN is configured, so callers
never need to guard against missing Sentry credentials.
"""

import logging
import os

_log = logging.getLogger(__name__)

_initialized = False


def init_sentry() -> None:
    """Initialize Sentry SDK if *SENTRY_DSN* is set in the environment."""
    global _initialized
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        _log.debug("SENTRY_DSN not set; Sentry error reporting disabled.")
        return
    try:
        import sentry_sdk  # noqa: F811

        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=0.0,  # no performance tracing for the desktop client
            environment=os.environ.get("NUDGE_ENVIRONMENT", "production").strip() or "production",
        )
        _initialized = True
        _log.info("Sentry error reporting initialised.")
    except Exception:
        _log.warning("Failed to initialise Sentry SDK.", exc_info=True)


def capture_exception(exc: BaseException | None = None) -> None:
    """Report *exc* (or the current ``sys.exc_info()``) to Sentry.

    No-op when Sentry is not initialised.
    """
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        _log.debug("sentry capture_exception failed", exc_info=True)


def set_user_context(principal: str) -> None:
    """Tag future Sentry events with the license principal identifier.

    No-op when Sentry is not initialised.
    """
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.set_user({"id": principal})
    except Exception:
        _log.debug("sentry set_user failed", exc_info=True)
