"""
Metrics configuration and alert rule definitions.

This module provides pre-configured alert rules, thresholds, and monitoring
configurations for production-grade observability of the AI Content Pipeline.

Configurations include:
- Success rate monitoring with configurable thresholds
- Error rate tracking with severity levels
- Performance degradation detection
- Data freshness monitoring
- Circuit breaker state tracking
- Resource utilization alerts
"""

from typing import Dict, List, Any
from .metrics import AlertRule, AlertSeverity, get_registry


# Alert Rules Configuration
ALERT_RULES = [
    # API Success Rate Monitoring
    AlertRule(
        name="api_success_rate_warning",
        metric_name="api.success_rate",
        condition="lt",
        threshold=0.8,  # 80%
        severity=AlertSeverity.WARNING,
        cooldown_seconds=300,  # 5 minutes
        description="API success rate dropped below 80%",
        enabled=True,
    ),
    AlertRule(
        name="api_success_rate_critical",
        metric_name="api.success_rate",
        condition="lt",
        threshold=0.5,  # 50%
        severity=AlertSeverity.CRITICAL,
        cooldown_seconds=180,  # 3 minutes
        description="API success rate dropped below 50%",
        enabled=True,
    ),
    # Error Rate Monitoring
    AlertRule(
        name="error_rate_warning",
        metric_name="error_rate_percent",
        condition="gt",
        threshold=20.0,  # 20%
        severity=AlertSeverity.WARNING,
        cooldown_seconds=300,
        description="Error rate exceeded 20%",
        enabled=True,
    ),
    AlertRule(
        name="error_rate_critical",
        metric_name="error_rate_percent",
        condition="gt",
        threshold=50.0,  # 50%
        severity=AlertSeverity.CRITICAL,
        cooldown_seconds=180,
        description="Error rate exceeded 50%",
        enabled=True,
    ),
    # Performance Monitoring
    AlertRule(
        name="sync_duration_warning",
        metric_name="sync.duration.p95",
        condition="gt",
        threshold=1800,  # 30 minutes
        severity=AlertSeverity.WARNING,
        cooldown_seconds=600,  # 10 minutes
        description="Sync operations taking longer than 30 minutes (P95)",
        enabled=True,
    ),
    AlertRule(
        name="sync_duration_critical",
        metric_name="sync.duration.p95",
        condition="gt",
        threshold=3600,  # 1 hour
        severity=AlertSeverity.CRITICAL,
        cooldown_seconds=300,  # 5 minutes
        description="Sync operations taking longer than 1 hour (P95)",
        enabled=True,
    ),
    # Data Freshness Monitoring
    AlertRule(
        name="data_freshness_warning",
        metric_name="data.last_sync_age_hours",
        condition="gt",
        threshold=6,  # 6 hours
        severity=AlertSeverity.WARNING,
        cooldown_seconds=1800,  # 30 minutes
        description="Data is older than 6 hours",
        enabled=True,
    ),
    AlertRule(
        name="data_freshness_critical",
        metric_name="data.last_sync_age_hours",
        condition="gt",
        threshold=24,  # 24 hours
        severity=AlertSeverity.CRITICAL,
        cooldown_seconds=900,  # 15 minutes
        description="Data is older than 24 hours",
        enabled=True,
    ),
    # Circuit Breaker Monitoring
    AlertRule(
        name="circuit_breaker_open",
        metric_name="circuit_breaker.state",
        condition="eq",
        threshold=1,  # Open state
        severity=AlertSeverity.WARNING,
        cooldown_seconds=60,  # 1 minute
        description="Circuit breaker is open",
        enabled=True,
    ),
    # Resource Utilization
    AlertRule(
        name="memory_usage_high",
        metric_name="system.memory_usage_percent",
        condition="gt",
        threshold=85.0,  # 85%
        severity=AlertSeverity.WARNING,
        cooldown_seconds=300,
        description="Memory usage exceeded 85%",
        enabled=True,
    ),
    AlertRule(
        name="cpu_usage_high",
        metric_name="system.cpu_usage_percent",
        condition="gt",
        threshold=90.0,  # 90%
        severity=AlertSeverity.WARNING,
        cooldown_seconds=300,
        description="CPU usage exceeded 90%",
        enabled=True,
    ),
    # Queue Monitoring
    AlertRule(
        name="queue_depth_warning",
        metric_name="queue.depth",
        condition="gt",
        threshold=1000,  # 1000 items
        severity=AlertSeverity.WARNING,
        cooldown_seconds=300,
        description="Queue depth exceeded 1000 items",
        enabled=True,
    ),
    AlertRule(
        name="queue_depth_critical",
        metric_name="queue.depth",
        condition="gt",
        threshold=5000,  # 5000 items
        severity=AlertSeverity.CRITICAL,
        cooldown_seconds=180,
        description="Queue depth exceeded 5000 items",
        enabled=True,
    ),
]


# Circuit Breaker Configuration
CIRCUIT_BREAKER_CONFIG = {
    "failure_threshold": 5,  # failures before opening
    "recovery_timeout": 60,  # seconds before attempting recovery
    "success_threshold": 3,  # successes needed to close circuit
    "monitoring_window": 300,  # 5 minutes rolling window
}


# Performance Monitoring Thresholds
PERFORMANCE_THRESHOLDS = {
    "api_response_time_p95": 5.0,  # 5 seconds
    "api_response_time_p99": 15.0,  # 15 seconds
    "sync_operation_timeout": 7200,  # 2 hours
    "batch_processing_timeout": 1800,  # 30 minutes
    "image_generation_timeout": 300,  # 5 minutes
    "video_generation_timeout": 1800,  # 30 minutes
}


# Health Check Configurations
HEALTH_CHECK_CONFIG = {
    "api_endpoints": {
        "timeout": 10,  # seconds
        "retries": 3,
        "backoff_factor": 0.3,
    },
    "database": {"connection_timeout": 5, "query_timeout": 30, "pool_size_check": True},
    "external_services": {
        "fal_ai": {"timeout": 5, "expected_status": 200},
        "elevenlabs": {"timeout": 5, "expected_status": 200},
        "gemini": {"timeout": 10, "expected_status": 200},
    },
    "filesystem": {
        "required_paths": ["output/", "temp/", "logs/"],
        "min_free_space_gb": 10,
    },
}


# Metric Collection Intervals
METRIC_COLLECTION_CONFIG = {
    "system_metrics_interval": 30,  # seconds
    "health_check_interval": 60,  # seconds
    "alert_evaluation_interval": 30,  # seconds
    "metric_cleanup_interval": 3600,  # 1 hour
}


# Alert Notification Channels (configurable)
NOTIFICATION_CONFIG = {
    "enabled_channels": ["log", "webhook"],  # Can be extended to email, slack, etc.
    "webhook": {
        "url": None,  # Set via environment variable
        "timeout": 5,
        "retries": 3,
    },
    "severity_filters": {
        "log": [
            AlertSeverity.INFO,
            AlertSeverity.WARNING,
            AlertSeverity.ERROR,
            AlertSeverity.CRITICAL,
        ],
        "webhook": [AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL],
    },
}


def initialize_alert_rules() -> None:
    """Initialize and register all predefined alert rules."""
    registry = get_registry()

    for rule in ALERT_RULES:
        registry.add_alert_rule(rule)

    print(f"Initialized {len(ALERT_RULES)} alert rules")


def get_health_check_thresholds() -> Dict[str, Any]:
    """Get health check scoring thresholds."""
    return {
        "api_response_time": {
            "healthy": PERFORMANCE_THRESHOLDS["api_response_time_p95"] * 0.5,
            "degraded": PERFORMANCE_THRESHOLDS["api_response_time_p95"] * 0.8,
            "unhealthy": PERFORMANCE_THRESHOLDS["api_response_time_p95"] * 1.5,
        },
        "error_rate": {
            "healthy": 5.0,  # 5%
            "degraded": 15.0,  # 15%
            "unhealthy": 30.0,  # 30%
        },
        "success_rate": {
            "healthy": 0.95,  # 95%
            "degraded": 0.85,  # 85%
            "unhealthy": 0.7,  # 70%
        },
        "data_freshness_hours": {
            "healthy": 1,  # 1 hour
            "degraded": 6,  # 6 hours
            "unhealthy": 24,  # 24 hours
        },
    }


def get_monitoring_config() -> Dict[str, Any]:
    """Get complete monitoring configuration."""
    return {
        "alert_rules": ALERT_RULES,
        "circuit_breaker": CIRCUIT_BREAKER_CONFIG,
        "performance_thresholds": PERFORMANCE_THRESHOLDS,
        "health_checks": HEALTH_CHECK_CONFIG,
        "collection_intervals": METRIC_COLLECTION_CONFIG,
        "notifications": NOTIFICATION_CONFIG,
        "health_thresholds": get_health_check_thresholds(),
    }


def validate_configuration() -> List[str]:
    """
    Validate monitoring configuration for consistency and completeness.

    Returns:
        List of validation errors (empty if configuration is valid)
    """
    errors = []

    # Validate alert rules
    rule_names = set()
    for rule in ALERT_RULES:
        if rule.name in rule_names:
            errors.append(f"Duplicate alert rule name: {rule.name}")
        rule_names.add(rule.name)

        if not rule.metric_name:
            errors.append(f"Alert rule '{rule.name}' missing metric_name")

        if rule.condition not in ["gt", "lt", "eq", "ne"]:
            errors.append(
                f"Alert rule '{rule.name}' has invalid condition: {rule.condition}"
            )

    # Validate thresholds
    if (
        PERFORMANCE_THRESHOLDS["api_response_time_p99"]
        <= PERFORMANCE_THRESHOLDS["api_response_time_p95"]
    ):
        errors.append("P99 threshold must be greater than P95 threshold")

    # Validate circuit breaker config
    cb = CIRCUIT_BREAKER_CONFIG
    if cb["success_threshold"] > cb["failure_threshold"]:
        errors.append(
            "Circuit breaker success_threshold cannot exceed failure_threshold"
        )

    return errors


# Initialize on module import
if __name__ != "__main__":
    # Validate configuration when imported
    validation_errors = validate_configuration()
    if validation_errors:
        raise ValueError(f"Configuration validation failed: {validation_errors}")

    # Initialize alert rules
    initialize_alert_rules()
