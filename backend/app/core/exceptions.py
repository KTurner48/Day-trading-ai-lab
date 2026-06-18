"""Domain exceptions."""
from __future__ import annotations


class AppError(Exception):
    code = "app_error"
    status_code = 400

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class KillSwitchActiveError(AppError):
    code = "kill_switch_active"
    status_code = 409


class LiveOrderingNotEnabledError(AppError):
    code = "live_ordering_not_enabled"
    status_code = 403


class BrokerNotConfiguredError(AppError):
    code = "broker_not_configured"
    status_code = 422
