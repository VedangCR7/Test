"""
Production-grade metrics, alerting, and health monitoring system.

This module provides enterprise-level observability for the AI Content Pipeline
with thread-safe metrics collection, configurable alerting, and comprehensive
health monitoring capabilities.

Features:
- Thread-safe metrics collection (counters, gauges, histograms, timers)
- Configurable alerting with severity levels and cooldowns
- Automated health checks with multi-dimensional scoring
- Historical data retention with bounded memory usage
- RESTful monitoring endpoints integration ready

Usage:
    from monitoring.metrics import MetricsRegistry, record_request, increment_counter

    # Initialize registry
    registry = MetricsRegistry()

    # Record metrics
    record_request("api.generate_image", 1.2, success=True)
    increment_counter("api.calls", tags={"endpoint": "generate_image"})
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Union
import logging

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels for operational monitoring."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HealthStatus(Enum):
    """Health check status for system components."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class MetricPoint:
    """Individual metric data point with timestamp and metadata."""

    timestamp: float
    value: Union[int, float]
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Configurable alert rule with thresholds and conditions."""

    name: str
    metric_name: str
    condition: str  # "gt", "lt", "eq", "ne"
    threshold: Union[int, float]
    severity: AlertSeverity
    cooldown_seconds: int = 300  # 5 minutes default cooldown
    description: str = ""
    enabled: bool = True

    def evaluate(self, value: Union[int, float]) -> bool:
        """Evaluate if the alert condition is met."""
        if not self.enabled:
            return False

        if self.condition == "gt":
            return value > self.threshold
        elif self.condition == "lt":
            return value < self.threshold
        elif self.condition == "eq":
            return value == self.threshold
        elif self.condition == "ne":
            return value != self.threshold
        else:
            logger.warning(f"Unknown alert condition: {self.condition}")
            return False


@dataclass
class Alert:
    """Active alert instance with state tracking."""

    rule_name: str
    severity: AlertSeverity
    message: str
    value: Union[int, float]
    threshold: Union[int, float]
    triggered_at: float
    resolved_at: Optional[float] = None
    cooldown_until: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if alert is currently active."""
        return self.resolved_at is None

    @property
    def is_in_cooldown(self) -> bool:
        """Check if alert is in cooldown period."""
        return time.time() < self.cooldown_until


@dataclass
class HealthCheck:
    """Health check result with scoring and metadata."""

    name: str
    status: HealthStatus
    score: float  # 0.0 to 1.0, where 1.0 is perfectly healthy
    message: str
    checked_at: float
    details: Dict[str, Any] = field(default_factory=dict)
    response_time: Optional[float] = None


class MetricsRegistry:
    """
    Thread-safe metrics registry with bounded history and alerting.

    This is the core component that manages all metrics collection,
    storage, and alerting for the AI Content Pipeline.

    Features:
    - Thread-safe operations with fine-grained locking
    - Bounded history to prevent memory leaks
    - Configurable alert rules with cooldowns
    - Health check aggregation
    - Performance-optimized data structures
    """

    def __init__(self, max_history_size: int = 10000, retention_hours: int = 24):
        """
        Initialize the metrics registry.

        Args:
            max_history_size: Maximum number of metric points to retain
            retention_hours: Hours to retain historical data
        """
        self.max_history_size = max_history_size
        self.retention_hours = retention_hours
        self.retention_seconds = retention_hours * 3600

        # Thread-safe storage
        self._lock = threading.RLock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._metric_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_history_size)
        )

        # Alerting system
        self._alert_rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []

        # Health monitoring
        self._health_checks: Dict[str, HealthCheck] = {}
        self._health_check_functions: Dict[str, Callable[[], HealthCheck]] = {}

        # Performance tracking
        self._collection_start_time = time.time()
        self._total_collections = 0

        logger.info(
            f"Initialized MetricsRegistry with max_history={max_history_size}, retention={retention_hours}h"
        )

    def increment_counter(
        self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name
            value: Value to increment by (default: 1)
            tags: Optional tags for categorization
        """
        with self._lock:
            self._counters[name] += value
            self._record_point(name, self._counters[name], tags or {})

    def set_gauge(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Set a gauge metric to a specific value.

        Args:
            name: Metric name
            value: Value to set
            tags: Optional tags for categorization
        """
        with self._lock:
            self._gauges[name] = value
            self._record_point(name, value, tags or {})

    def record_histogram(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a value in a histogram metric.

        Args:
            name: Metric name
            value: Value to record
            tags: Optional tags for categorization
        """
        with self._lock:
            self._histograms[name].append(value)
            # Keep only last 1000 values for memory efficiency
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]
            self._record_point(name, value, tags or {})

    def record_timer(
        self, name: str, duration: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a timer/duration metric.

        Args:
            name: Metric name
            duration: Duration in seconds
            tags: Optional tags for categorization
        """
        with self._lock:
            self._timers[name].append(duration)
            # Keep only last 1000 values
            if len(self._timers[name]) > 1000:
                self._timers[name] = self._timers[name][-1000:]
            self._record_point(name, duration, tags or {})

    def _record_point(
        self, name: str, value: Union[int, float], tags: Dict[str, str]
    ) -> None:
        """Record a metric data point with timestamp."""
        point = MetricPoint(timestamp=time.time(), value=value, tags=tags)
        self._metric_history[name].append(point)
        self._total_collections += 1

        # Clean up old data periodically
        if self._total_collections % 1000 == 0:
            self._cleanup_old_data()

    def _cleanup_old_data(self) -> None:
        """Remove data points older than retention period."""
        cutoff_time = time.time() - self.retention_seconds
        for metric_name, history in self._metric_history.items():
            # Remove old points from deque
            while history and history[0].timestamp < cutoff_time:
                history.popleft()

    def get_counter(self, name: str) -> int:
        """Get current counter value."""
        with self._lock:
            return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> Optional[float]:
        """Get current gauge value."""
        with self._lock:
            return self._gauges.get(name)

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """Get histogram statistics."""
        with self._lock:
            values = self._histograms.get(name, [])
            if not values:
                return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}

            return {
                "count": len(values),
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
            }

    def get_timer_stats(self, name: str) -> Dict[str, float]:
        """Get timer statistics."""
        with self._lock:
            durations = self._timers.get(name, [])
            if not durations:
                return {
                    "count": 0,
                    "mean": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                }

            sorted_durations = sorted(durations)
            p95_index = int(len(sorted_durations) * 0.95)
            p99_index = int(len(sorted_durations) * 0.99)

            return {
                "count": len(durations),
                "mean": sum(durations) / len(durations),
                "min": min(durations),
                "max": max(durations),
                "p95": sorted_durations[min(p95_index, len(sorted_durations) - 1)],
                "p99": sorted_durations[min(p99_index, len(sorted_durations) - 1)],
            }

    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add an alert rule to the registry."""
        with self._lock:
            self._alert_rules[rule.name] = rule
            logger.info(f"Added alert rule: {rule.name}")

    def evaluate_alerts(self) -> List[Alert]:
        """Evaluate all alert rules and return triggered alerts."""
        triggered_alerts = []

        with self._lock:
            for rule_name, rule in self._alert_rules.items():
                if not rule.enabled:
                    continue

                # Get current metric value
                if rule.metric_name in self._counters:
                    current_value = self._counters[rule.metric_name]
                elif rule.metric_name in self._gauges:
                    current_value = self._gauges[rule.metric_name]
                else:
                    # For histograms/timers, use mean
                    if (
                        rule.metric_name in self._histograms
                        and self._histograms[rule.metric_name]
                    ):
                        current_value = sum(self._histograms[rule.metric_name]) / len(
                            self._histograms[rule.metric_name]
                        )
                    elif (
                        rule.metric_name in self._timers
                        and self._timers[rule.metric_name]
                    ):
                        current_value = sum(self._timers[rule.metric_name]) / len(
                            self._timers[rule.metric_name]
                        )
                    else:
                        continue

                # Check if alert should trigger
                if rule.evaluate(current_value):
                    alert_key = f"{rule_name}_{rule.metric_name}"

                    # Check if alert is already active or in cooldown
                    if alert_key in self._active_alerts:
                        existing_alert = self._active_alerts[alert_key]
                        if existing_alert.is_in_cooldown:
                            continue  # Skip, still in cooldown
                        elif existing_alert.is_active:
                            continue  # Already active
                    elif alert_key in [
                        a.rule_name for a in self._alert_history[-10:]
                    ]:  # Recent history
                        continue  # Recently triggered

                    # Create new alert
                    alert = Alert(
                        rule_name=rule_name,
                        severity=rule.severity,
                        message=f"{rule.description}: {current_value} {rule.condition} {rule.threshold}",
                        value=current_value,
                        threshold=rule.threshold,
                        triggered_at=time.time(),
                        cooldown_until=time.time() + rule.cooldown_seconds,
                        tags={"metric": rule.metric_name, "condition": rule.condition},
                    )

                    self._active_alerts[alert_key] = alert
                    self._alert_history.append(alert)
                    triggered_alerts.append(alert)

                    logger.warning(f"Alert triggered: {alert.message}")

        return triggered_alerts

    def resolve_alert(self, alert_key: str) -> bool:
        """Resolve an active alert."""
        with self._lock:
            if alert_key in self._active_alerts:
                alert = self._active_alerts[alert_key]
                alert.resolved_at = time.time()
                del self._active_alerts[alert_key]
                logger.info(f"Alert resolved: {alert.message}")
                return True
            return False

    def get_active_alerts(self) -> List[Alert]:
        """Get all currently active alerts."""
        with self._lock:
            return list(self._active_alerts.values())

    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """Get recent alert history."""
        with self._lock:
            return self._alert_history[-limit:]

    def register_health_check(
        self, name: str, check_function: Callable[[], HealthCheck]
    ) -> None:
        """Register a health check function."""
        with self._lock:
            self._health_check_functions[name] = check_function
            logger.info(f"Registered health check: {name}")

    def run_health_checks(self) -> Dict[str, HealthCheck]:
        """Run all registered health checks and return results."""
        results = {}

        for name, check_func in self._health_check_functions.items():
            try:
                start_time = time.time()
                result = check_func()
                result.response_time = time.time() - start_time
                results[name] = result

                with self._lock:
                    self._health_checks[name] = result

            except Exception as e:
                logger.error(f"Health check '{name}' failed: {e}")
                error_check = HealthCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    score=0.0,
                    message=f"Check failed: {str(e)}",
                    checked_at=time.time(),
                )
                results[name] = error_check

                with self._lock:
                    self._health_checks[name] = error_check

        return results

    def get_overall_health_score(self) -> float:
        """Calculate overall system health score (0.0 to 1.0)."""
        with self._lock:
            if not self._health_checks:
                return 1.0  # Assume healthy if no checks

            total_score = 0.0
            count = 0

            for check in self._health_checks.values():
                # Weight critical checks more heavily
                weight = 2.0 if check.status == HealthStatus.CRITICAL else 1.0
                total_score += check.score * weight
                count += weight

            return total_score / count if count > 0 else 0.0

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        """Get a complete snapshot of all metrics for monitoring endpoints."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    name: self.get_histogram_stats(name) for name in self._histograms
                },
                "timers": {name: self.get_timer_stats(name) for name in self._timers},
                "active_alerts": len(self._active_alerts),
                "health_score": self.get_overall_health_score(),
                "total_collections": self._total_collections,
                "uptime_seconds": time.time() - self._collection_start_time,
                "timestamp": time.time(),
            }

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._timers.clear()
            self._metric_history.clear()
            self._active_alerts.clear()
            self._alert_history.clear()
            self._health_checks.clear()
            self._total_collections = 0
            self._collection_start_time = time.time()
            logger.info("Metrics registry reset")


# Global registry instance
_global_registry = MetricsRegistry()


def get_registry() -> MetricsRegistry:
    """Get the global metrics registry instance."""
    return _global_registry


def increment_counter(
    name: str, value: int = 1, tags: Optional[Dict[str, str]] = None
) -> None:
    """Convenience function to increment a counter."""
    _global_registry.increment_counter(name, value, tags)


def set_gauge(name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Convenience function to set a gauge."""
    _global_registry.set_gauge(name, value, tags)


def record_histogram(
    name: str, value: float, tags: Optional[Dict[str, str]] = None
) -> None:
    """Convenience function to record a histogram value."""
    _global_registry.record_histogram(name, value, tags)


def record_timer(
    name: str, duration: float, tags: Optional[Dict[str, str]] = None
) -> None:
    """Convenience function to record a timer duration."""
    _global_registry.record_timer(name, duration, tags)


def record_request(
    endpoint: str,
    duration: float,
    success: bool = True,
    tags: Optional[Dict[str, str]] = None,
) -> None:
    """
    Convenience function to record an API request.

    Args:
        endpoint: API endpoint name
        duration: Request duration in seconds
        success: Whether the request was successful
        tags: Additional tags
    """
    final_tags = {"endpoint": endpoint, "success": str(success)}
    if tags:
        final_tags.update(tags)

    increment_counter("api.requests_total", tags=final_tags)
    record_timer(f"api.request_duration.{endpoint}", duration, final_tags)

    if not success:
        increment_counter("api.requests_failed", tags={"endpoint": endpoint})


def record_error(
    error_type: str, message: str = "", tags: Optional[Dict[str, str]] = None
) -> None:
    """
    Convenience function to record an error.

    Args:
        error_type: Type of error (e.g., "api_error", "processing_error")
        message: Error message
        tags: Additional tags
    """
    final_tags = {"error_type": error_type}
    if tags:
        final_tags.update(tags)

    increment_counter("errors_total", tags=final_tags)
    increment_counter(f"errors.{error_type}", tags=tags)


def record_data_processed(
    operation: str, count: int, duration: float, tags: Optional[Dict[str, str]] = None
) -> None:
    """
    Convenience function to record data processing metrics.

    Args:
        operation: Type of operation (e.g., "image_generation", "video_processing")
        count: Number of items processed
        duration: Processing duration in seconds
        tags: Additional tags
    """
    final_tags = {"operation": operation}
    if tags:
        final_tags.update(tags)

    increment_counter("data.processed_total", count, final_tags)
    record_timer(f"data.processing_duration.{operation}", duration, final_tags)
    set_gauge(
        f"data.processing_rate.{operation}",
        count / duration if duration > 0 else 0,
        final_tags,
    )
