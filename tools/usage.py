"""AI-facing tool for App Usage Insights ("how long did I code today?")."""

from core import app_usage


def get_usage_summary(period: str = "today", category: str = "") -> dict:
    return app_usage.get_usage_summary(period, category)
