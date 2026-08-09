"""Prometheus metrics served on /metrics (design doc section 7)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

todoist_api_requests_total = Counter(
    "todoist_api_requests_total",
    "Todoist API call attempts",
    ["operation", "outcome"],  # outcome: success | retry | failure
)

todoist_api_failures_total = Counter(
    "todoist_api_failures_total",
    "Todoist API calls that failed after retries were exhausted",
    ["operation"],
)

todoist_auth_failures_total = Counter(
    "todoist_auth_failures_total",
    "Todoist API calls that failed with 401/403 (expired or revoked token)",
    ["operation"],
)

todoist_api_call_duration_seconds = Histogram(
    "todoist_api_call_duration_seconds",
    "Todoist API call latency",
    ["operation"],
)

tasks_created_total = Counter(
    "tasks_created_total",
    "Successful birthday reminders created",
)

people_checked_total = Counter(
    "people_checked_total",
    "People evaluated during a reminder run",
)

reminder_run_last_success_timestamp = Gauge(
    "reminder_run_last_success_timestamp",
    "Unix time of the last fully-successful run",
)

reminder_run_last_run_timestamp = Gauge(
    "reminder_run_last_run_timestamp",
    "Unix time of the last attempted run, success or not",
)
