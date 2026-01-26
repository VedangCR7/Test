"""
Comprehensive unit tests for core metrics functionality.

Tests cover thread safety, metric collection, alerting, and health monitoring.
"""

import pytest
import time
import threading
from unittest.mock import patch

from ..metrics import (
    MetricsRegistry,
    AlertRule,
    AlertSeverity,
    HealthStatus,
    increment_counter,
    set_gauge,
    record_histogram,
    record_timer,
    record_request,
    record_error,
    record_data_processed,
    get_registry,
)


class TestMetricsRegistry:
    """Test MetricsRegistry core functionality."""

    def test_registry_initialization(self):
        """Test registry initializes with correct defaults."""
        registry = MetricsRegistry(max_history_size=1000, retention_hours=12)

        assert registry.max_history_size == 1000
        assert registry.retention_hours == 12
        assert registry.retention_seconds == 12 * 3600
        assert len(registry._counters) == 0
        assert len(registry._gauges) == 0
        assert len(registry._alert_rules) == 0

    def test_counter_operations(self):
        """Test counter increment operations."""
        registry = MetricsRegistry()

        # Test basic increment
        registry.increment_counter("test_counter")
        assert registry.get_counter("test_counter") == 1

        # Test increment by value
        registry.increment_counter("test_counter", 5)
        assert registry.get_counter("test_counter") == 6

        # Test with tags
        registry.increment_counter("tagged_counter", tags={"env": "test"})
        assert registry.get_counter("tagged_counter") == 1

    def test_gauge_operations(self):
        """Test gauge set operations."""
        registry = MetricsRegistry()

        # Test gauge setting
        registry.set_gauge("test_gauge", 42.5)
        assert registry.get_gauge("test_gauge") == 42.5

        # Test gauge update
        registry.set_gauge("test_gauge", 100.0)
        assert registry.get_gauge("test_gauge") == 100.0

        # Test with tags
        registry.set_gauge("tagged_gauge", 75.0, tags={"unit": "percent"})
        assert registry.get_gauge("tagged_gauge") == 75.0

    def test_histogram_operations(self):
        """Test histogram recording and statistics."""
        registry = MetricsRegistry()

        # Record histogram values
        values = [10, 20, 30, 40, 50]
        for value in values:
            registry.record_histogram("test_histogram", value)

        stats = registry.get_histogram_stats("test_histogram")
        assert stats["count"] == 5
        assert stats["mean"] == 30.0
        assert stats["min"] == 10
        assert stats["max"] == 50

    def test_timer_operations(self):
        """Test timer recording and statistics."""
        registry = MetricsRegistry()

        # Record timer durations
        durations = [0.1, 0.2, 0.3, 0.4, 0.5]
        for duration in durations:
            registry.record_timer("test_timer", duration)

        stats = registry.get_timer_stats("test_timer")
        assert stats["count"] == 5
        assert stats["mean"] == 0.3
        assert stats["min"] == 0.1
        assert stats["max"] == 0.5
        assert stats["p95"] == 0.46  # Approximately 95th percentile
        assert stats["p99"] == 0.49  # Approximately 99th percentile

    def test_metric_history_tracking(self):
        """Test that metrics are properly tracked in history."""
        registry = MetricsRegistry(max_history_size=10)

        # Record some metrics
        registry.increment_counter("test_counter")
        registry.set_gauge("test_gauge", 100.0)
        registry.record_histogram("test_histogram", 50.0)

        # Check history
        assert len(registry._metric_history["test_counter"]) == 1
        assert len(registry._metric_history["test_gauge"]) == 1
        assert len(registry._metric_history["test_histogram"]) == 1

        # Check metric point structure
        point = registry._metric_history["test_counter"][0]
        assert hasattr(point, "timestamp")
        assert hasattr(point, "value")
        assert hasattr(point, "tags")
        assert point.value == 1

    def test_history_size_limits(self):
        """Test that history respects size limits."""
        registry = MetricsRegistry(max_history_size=3)

        # Add more points than max_history_size
        for i in range(5):
            registry.increment_counter("test_counter")

        # Should only keep the last 3
        assert len(registry._metric_history["test_counter"]) == 3
        assert registry.get_counter("test_counter") == 5  # Total count is still correct

    def test_data_retention_cleanup(self):
        """Test that old data is cleaned up based on retention policy."""
        registry = MetricsRegistry(retention_hours=0.001)  # Very short retention

        # Add some data
        registry.increment_counter("test_counter")
        initial_history_len = len(registry._metric_history["test_counter"])

        # Wait longer than retention period
        time.sleep(0.01)  # 10ms > 0.001 hours

        # Trigger cleanup
        registry._cleanup_old_data()

        # Old data should be cleaned up
        assert len(registry._metric_history["test_counter"]) < initial_history_len

    def test_thread_safety(self):
        """Test that registry operations are thread-safe."""
        registry = MetricsRegistry()
        results = []

        def worker_thread(thread_id):
            """Worker function for thread safety testing."""
            for i in range(100):
                registry.increment_counter(f"thread_counter_{thread_id}")
                registry.set_gauge(f"thread_gauge_{thread_id}", i)
                time.sleep(0.001)  # Small delay to encourage race conditions

            results.append(f"thread_{thread_id}_done")

        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify results
        assert len(results) == 5
        for i in range(5):
            assert registry.get_counter(f"thread_counter_{i}") == 100
            assert registry.get_gauge(f"thread_gauge_{i}") == 99  # Last value set

    def test_registry_reset(self):
        """Test registry reset functionality."""
        registry = MetricsRegistry()

        # Add some data
        registry.increment_counter("test_counter", 10)
        registry.set_gauge("test_gauge", 50.0)
        registry.record_histogram("test_histogram", 25.0)
        registry.record_timer("test_timer", 0.5)

        # Verify data exists
        assert registry.get_counter("test_counter") == 10
        assert registry.get_gauge("test_gauge") == 50.0
        assert registry.get_histogram_stats("test_histogram")["count"] == 1

        # Reset registry
        registry.reset()

        # Verify data is cleared
        assert registry.get_counter("test_counter") == 0
        assert registry.get_gauge("test_gauge") is None
        assert registry.get_histogram_stats("test_histogram")["count"] == 0
        assert registry.get_timer_stats("test_timer")["count"] == 0

        # But collections counter should restart
        assert registry._total_collections == 0


class TestAlertSystem:
    """Test alerting system functionality."""

    def test_alert_rule_creation(self):
        """Test alert rule creation and validation."""
        rule = AlertRule(
            name="test_rule",
            metric_name="test_counter",
            condition="gt",
            threshold=100,
            severity=AlertSeverity.WARNING,
            description="Test alert rule",
        )

        assert rule.name == "test_rule"
        assert rule.metric_name == "test_counter"
        assert rule.condition == "gt"
        assert rule.threshold == 100
        assert rule.severity == AlertSeverity.WARNING
        assert rule.enabled is True

    def test_alert_rule_evaluation(self):
        """Test alert rule evaluation logic."""
        # Greater than rule
        gt_rule = AlertRule("gt_test", "test_metric", "gt", 50, AlertSeverity.WARNING)
        assert gt_rule.evaluate(75) is True
        assert gt_rule.evaluate(25) is False
        assert gt_rule.evaluate(50) is False

        # Less than rule
        lt_rule = AlertRule("lt_test", "test_metric", "lt", 50, AlertSeverity.WARNING)
        assert lt_rule.evaluate(25) is True
        assert lt_rule.evaluate(75) is False
        assert lt_rule.evaluate(50) is False

        # Equal rule
        eq_rule = AlertRule("eq_test", "test_metric", "eq", 50, AlertSeverity.WARNING)
        assert eq_rule.evaluate(50) is True
        assert eq_rule.evaluate(25) is False

        # Not equal rule
        ne_rule = AlertRule("ne_test", "test_metric", "ne", 50, AlertSeverity.WARNING)
        assert ne_rule.evaluate(25) is True
        assert ne_rule.evaluate(50) is False

    def test_disabled_alert_rule(self):
        """Test that disabled alert rules don't trigger."""
        rule = AlertRule(
            "disabled_test",
            "test_metric",
            "gt",
            50,
            AlertSeverity.WARNING,
            enabled=False,
        )
        assert rule.evaluate(75) is False

    def test_invalid_condition(self):
        """Test handling of invalid alert conditions."""
        rule = AlertRule(
            "invalid_test", "test_metric", "invalid", 50, AlertSeverity.WARNING
        )

        # Should return False for invalid conditions
        with patch("src.monitoring.metrics.logger") as mock_logger:
            assert rule.evaluate(75) is False
            mock_logger.warning.assert_called_once()

    def test_registry_alert_integration(self):
        """Test alert rule integration with registry."""
        registry = MetricsRegistry()

        # Add alert rule
        rule = AlertRule(
            "counter_alert", "test_counter", "gt", 5, AlertSeverity.WARNING
        )
        registry.add_alert_rule(rule)

        assert "counter_alert" in registry._alert_rules

        # Increment counter below threshold
        registry.increment_counter("test_counter", 3)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 0

        # Increment counter above threshold
        registry.increment_counter("test_counter", 3)  # Total: 6
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1
        assert alerts[0].rule_name == "counter_alert"
        assert alerts[0].severity == AlertSeverity.WARNING

    def test_alert_cooldown(self):
        """Test alert cooldown functionality."""
        registry = MetricsRegistry()

        rule = AlertRule(
            "cooldown_test",
            "test_counter",
            "gt",
            5,
            AlertSeverity.WARNING,
            cooldown_seconds=1,
        )
        registry.add_alert_rule(rule)

        # Trigger alert
        registry.increment_counter("test_counter", 10)
        alerts1 = registry.evaluate_alerts()
        assert len(alerts1) == 1

        # Try to trigger again immediately (should be in cooldown)
        registry.increment_counter("test_counter", 10)
        alerts2 = registry.evaluate_alerts()
        assert len(alerts2) == 0  # Should be in cooldown

        # Wait for cooldown to expire
        time.sleep(1.1)
        alerts3 = registry.evaluate_alerts()
        assert len(alerts3) == 1  # Should trigger again

    def test_active_alert_tracking(self):
        """Test active alert tracking and resolution."""
        registry = MetricsRegistry()

        rule = AlertRule("active_test", "test_counter", "gt", 5, AlertSeverity.ERROR)
        registry.add_alert_rule(rule)

        # Trigger alert
        registry.increment_counter("test_counter", 10)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1
        assert len(registry.get_active_alerts()) == 1

        alert_id = f"{alerts[0].rule_name}_{alerts[0].triggered_at}"

        # Try to resolve non-existent alert
        assert registry.resolve_alert("nonexistent") is False

        # Resolve the actual alert
        assert registry.resolve_alert(alert_id) is True
        assert len(registry.get_active_alerts()) == 0

    def test_alert_history(self):
        """Test alert history tracking."""
        registry = MetricsRegistry()

        rule = AlertRule("history_test", "test_counter", "gt", 5, AlertSeverity.INFO)
        registry.add_alert_rule(rule)

        # Trigger multiple alerts
        for i in range(3):
            registry.increment_counter("test_counter", 10)
            registry.evaluate_alerts()
            time.sleep(0.01)  # Ensure different timestamps

        # Check history
        history = registry.get_alert_history()
        assert len(history) == 3

        # Check history limit
        limited_history = registry.get_alert_history(limit=2)
        assert len(limited_history) == 2


class TestHealthMonitoring:
    """Test health monitoring functionality."""

    def test_health_check_registration(self):
        """Test health check function registration."""
        registry = MetricsRegistry()

        def mock_health_check():
            return registry.HealthCheck(
                name="test_check",
                status=HealthStatus.HEALTHY,
                score=1.0,
                message="All good",
                checked_at=time.time(),
            )

        registry.register_health_check("test_check", mock_health_check)
        assert "test_check" in registry._health_check_functions

    def test_health_check_execution(self):
        """Test health check execution and result storage."""
        registry = MetricsRegistry()

        call_count = 0

        def mock_health_check():
            nonlocal call_count
            call_count += 1
            return registry.HealthCheck(
                name="execution_test",
                status=HealthStatus.HEALTHY,
                score=0.9,
                message="Test check",
                checked_at=time.time(),
                response_time=0.1,
            )

        registry.register_health_check("execution_test", mock_health_check)

        # Run health checks
        results = registry.run_health_checks()

        assert "execution_test" in results
        assert call_count == 1
        assert results["execution_test"].status == HealthStatus.HEALTHY
        assert results["execution_test"].score == 0.9
        assert results["execution_test"].response_time == 0.1

        # Check stored results
        assert "execution_test" in registry._health_checks

    def test_health_check_error_handling(self):
        """Test health check error handling."""
        registry = MetricsRegistry()

        def failing_health_check():
            raise Exception("Test failure")

        registry.register_health_check("failing_check", failing_health_check)

        results = registry.run_health_checks()

        assert "failing_check" in results
        assert results["failing_check"].status == HealthStatus.UNHEALTHY
        assert results["failing_check"].score == 0.0
        assert "Test failure" in results["failing_check"].message

    def test_overall_health_score_calculation(self):
        """Test overall health score calculation."""
        registry = MetricsRegistry()

        # Register multiple health checks
        checks = [
            ("healthy_check", HealthStatus.HEALTHY, 1.0),
            ("degraded_check", HealthStatus.DEGRADED, 0.7),
            ("unhealthy_check", HealthStatus.UNHEALTHY, 0.2),
        ]

        for name, status, score in checks:

            def create_check(check_name, check_status, check_score):
                def check():
                    return registry.HealthCheck(
                        name=check_name,
                        status=check_status,
                        score=check_score,
                        message=f"{check_name} status",
                        checked_at=time.time(),
                    )

                return check

            registry.register_health_check(name, create_check(name, status, score))
            registry._health_checks[name] = registry.HealthCheck(
                name=name,
                status=status,
                score=score,
                message=f"{name} status",
                checked_at=time.time(),
            )

        overall_score = registry.get_overall_health_score()
        # Should be average of all scores
        expected_score = (1.0 + 0.7 + 0.2) / 3
        assert abs(overall_score - expected_score) < 0.001

    def test_empty_registry_health_score(self):
        """Test health score when no checks are registered."""
        registry = MetricsRegistry()

        # Empty registry should return perfect health
        assert registry.get_overall_health_score() == 1.0

    def test_health_score_weighting(self):
        """Test health score weighting for critical checks."""
        registry = MetricsRegistry()

        # Add critical and normal checks
        checks = [
            ("critical_healthy", HealthStatus.HEALTHY, 1.0, True),
            ("normal_degraded", HealthStatus.DEGRADED, 0.7, False),
        ]

        total_weight = 0
        total_score = 0

        for name, status, score, is_critical in checks:
            weight = 2.0 if is_critical else 1.0
            registry._health_checks[name] = registry.HealthCheck(
                name=name,
                status=status,
                score=score,
                message=f"{name} status",
                checked_at=time.time(),
            )
            total_score += score * weight
            total_weight += weight

        overall_score = registry.get_overall_health_score()
        expected_score = total_score / total_weight
        assert abs(overall_score - expected_score) < 0.001


class TestConvenienceFunctions:
    """Test convenience functions for easy metric recording."""

    def test_increment_counter_convenience(self):
        """Test increment_counter convenience function."""
        registry = get_registry()
        initial_count = registry.get_counter("convenience_test")

        increment_counter("convenience_test", 5)
        assert registry.get_counter("convenience_test") == initial_count + 5

    def test_set_gauge_convenience(self):
        """Test set_gauge convenience function."""
        registry = get_registry()

        set_gauge("convenience_gauge", 42.0)
        assert registry.get_gauge("convenience_gauge") == 42.0

    def test_record_histogram_convenience(self):
        """Test record_histogram convenience function."""
        registry = get_registry()

        record_histogram("convenience_histogram", 25.0)
        stats = registry.get_histogram_stats("convenience_histogram")
        assert stats["count"] == 1
        assert stats["mean"] == 25.0

    def test_record_timer_convenience(self):
        """Test record_timer convenience function."""
        registry = get_registry()

        record_timer("convenience_timer", 0.5)
        stats = registry.get_timer_stats("convenience_timer")
        assert stats["count"] == 1
        assert stats["mean"] == 0.5

    def test_record_request_convenience(self):
        """Test record_request convenience function."""
        registry = get_registry()
        initial_total = registry.get_counter("api.requests_total")

        record_request("test_endpoint", 1.2, success=True)

        # Check counters
        assert registry.get_counter("api.requests_total") == initial_total + 1
        assert registry.get_counter("api.requests_failed") == 0

        # Check timer
        timer_stats = registry.get_timer_stats("api.request_duration.test_endpoint")
        assert timer_stats["count"] == 1
        assert timer_stats["mean"] == 1.2

    def test_record_request_with_failure(self):
        """Test record_request with failure."""
        registry = get_registry()

        record_request("fail_endpoint", 0.8, success=False)

        assert registry.get_counter("api.requests_failed") == 1
        assert registry.get_counter("api.requests_total") == 1

    def test_record_error_convenience(self):
        """Test record_error convenience function."""
        registry = get_registry()

        record_error("test_error", "Test error message")

        assert registry.get_counter("errors_total") >= 1
        assert registry.get_counter("errors.test_error") >= 1

    def test_record_data_processed_convenience(self):
        """Test record_data_processed convenience function."""
        registry = get_registry()

        record_data_processed("image_generation", 10, 2.5)

        assert registry.get_counter("data.processed_total") == 10
        assert (
            registry.get_gauge("data.processing_rate.image_generation") == 4.0
        )  # 10/2.5

        timer_stats = registry.get_timer_stats(
            "data.processing_duration.image_generation"
        )
        assert timer_stats["count"] == 1
        assert timer_stats["mean"] == 2.5


class TestMetricsSnapshot:
    """Test metrics snapshot functionality."""

    def test_metrics_snapshot_structure(self):
        """Test that metrics snapshot has correct structure."""
        registry = MetricsRegistry()

        # Add some test data
        registry.increment_counter("test_counter", 5)
        registry.set_gauge("test_gauge", 100.0)
        registry.record_histogram("test_histogram", 50.0)
        registry.record_timer("test_timer", 0.5)

        snapshot = registry.get_metrics_snapshot()

        required_keys = [
            "counters",
            "gauges",
            "histograms",
            "timers",
            "active_alerts",
            "health_score",
            "total_collections",
            "uptime_seconds",
            "timestamp",
        ]
        for key in required_keys:
            assert key in snapshot

        assert snapshot["counters"]["test_counter"] == 5
        assert snapshot["gauges"]["test_gauge"] == 100.0
        assert snapshot["histograms"]["test_histogram"]["count"] == 1
        assert snapshot["timers"]["test_timer"]["count"] == 1
        assert isinstance(snapshot["timestamp"], (int, float))

    def test_snapshot_with_computed_metrics(self):
        """Test snapshot with computed metrics like success rate."""
        registry = MetricsRegistry()

        # Simulate API request metrics
        registry._counters["api.requests_total"] = 100
        registry._counters["api.requests_failed"] = 20

        snapshot = registry.get_metrics_snapshot()

        assert "computed" in snapshot
        assert snapshot["computed"]["api_success_rate"] == 0.8  # 80%
        assert snapshot["computed"]["error_rate_percent"] == 20.0

    def test_empty_snapshot(self):
        """Test snapshot with no metrics."""
        registry = MetricsRegistry()

        snapshot = registry.get_metrics_snapshot()

        assert snapshot["counters"] == {}
        assert snapshot["gauges"] == {}
        assert snapshot["histograms"] == {}
        assert snapshot["timers"] == {}
        assert snapshot["active_alerts"] == 0
        assert snapshot["health_score"] == 1.0  # Default for no checks
        assert snapshot["total_collections"] == 0
        assert isinstance(snapshot["uptime_seconds"], (int, float))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
