"""
AI Content Pipeline Monitoring and Alerting System.

This package provides comprehensive production-grade monitoring capabilities
including metrics collection, alerting, health checks, and RESTful APIs.

Key Features:
- Thread-safe metrics collection (counters, gauges, histograms, timers)
- Configurable alerting with severity levels and cooldowns
- Automated health checks with multi-dimensional scoring
- RESTful monitoring endpoints for operational visibility
- CLI commands for monitoring and diagnostics

Quick Start:
    from ai_content_pipeline.monitoring import get_registry, record_request

    # Record a successful API request
    record_request("api.generate_image", 1.2, success=True)

    # Start monitoring API server
    from ai_content_pipeline.monitoring.api import start_monitoring_server
    server = start_monitoring_server(port=8080)
"""

from .metrics import (
    # Core classes
    MetricsRegistry,
    AlertSeverity,
    HealthStatus,
    # Main functions
    get_registry,
    increment_counter,
    set_gauge,
    record_histogram,
    record_timer,
    record_request,
    record_error,
    # Convenience functions
    record_data_processed,
)

from .metrics_config import (
    ALERT_RULES,
    CIRCUIT_BREAKER_CONFIG,
    PERFORMANCE_THRESHOLDS,
    HEALTH_CHECK_CONFIG,
    initialize_alert_rules,
    validate_configuration,
    get_monitoring_config,
    get_health_check_thresholds,
)

from .api import (
    MonitoringAPIServer,
    start_monitoring_server,
    get_metrics_endpoint,
    get_health_endpoint,
    get_alerts_endpoint,
    initialize_monitoring_api,
    shutdown_monitoring_api,
)

__version__ = "1.0.0"

__all__ = [
    # Core metrics
    "MetricsRegistry",
    "AlertSeverity",
    "HealthStatus",
    "get_registry",
    "increment_counter",
    "set_gauge",
    "record_histogram",
    "record_timer",
    "record_request",
    "record_error",
    "record_data_processed",
    # Configuration
    "ALERT_RULES",
    "CIRCUIT_BREAKER_CONFIG",
    "PERFORMANCE_THRESHOLDS",
    "HEALTH_CHECK_CONFIG",
    "initialize_alert_rules",
    "validate_configuration",
    "get_monitoring_config",
    "get_health_check_thresholds",
    # API
    "MonitoringAPIServer",
    "start_monitoring_server",
    "get_metrics_endpoint",
    "get_health_endpoint",
    "get_alerts_endpoint",
    "initialize_monitoring_api",
    "shutdown_monitoring_api",
]
