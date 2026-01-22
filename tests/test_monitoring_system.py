"""
Comprehensive tests for the monitoring and alerting system.

Tests cover:
- Thread-safe metrics collection
- Alert rule evaluation
- Health check functionality
- API endpoints
- CLI monitoring commands
- Integration across components
"""

import pytest
import time
import threading
import json
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add the packages to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "core" / "ai_content_pipeline"))

from ai_content_pipeline.monitoring.metrics import (
    MetricsRegistry, AlertSeverity, HealthStatus, get_registry,
    increment_counter, set_gauge, record_histogram, record_timer,
    record_request, record_error, AlertRule
)
from ai_content_pipeline.monitoring.metrics_config import (
    ALERT_RULES, validate_configuration, get_health_check_thresholds
)


class TestMetricsRegistry:
    """Test the core metrics registry functionality."""

    def test_registry_initialization(self):
        """Test registry initializes with correct defaults."""
        registry = MetricsRegistry()
        assert registry.max_history_size == 10000
        assert registry._lock is not None
        assert len(registry._counters) == 0
        assert len(registry._gauges) == 0

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

        registry.set_gauge("test_gauge", 42.5)
        assert registry.get_gauge("test_gauge") == 42.5

        registry.set_gauge("test_gauge", 50.0)
        assert registry.get_gauge("test_gauge") == 50.0

    def test_histogram_operations(self):
        """Test histogram recording and statistics."""
        registry = MetricsRegistry()

        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for value in values:
            registry.record_histogram("test_histogram", value)

        stats = registry.get_histogram_stats("test_histogram")
        assert stats["count"] == 5
        assert stats["mean"] == 3.0
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0

    def test_timer_operations(self):
        """Test timer recording and statistics."""
        registry = MetricsRegistry()

        durations = [0.1, 0.2, 0.3, 0.4, 0.5]
        for duration in durations:
            registry.record_timer("test_timer", duration)

        stats = registry.get_timer_stats("test_timer")
        assert stats["count"] == 5
        assert stats["mean"] == 0.3
        assert stats["p95"] == 0.5  # All values below 0.5, so max

    def test_thread_safety(self):
        """Test thread-safe operations under concurrent access."""
        registry = MetricsRegistry()
        results = []

        def worker(worker_id):
            """Worker function for concurrent testing."""
            for i in range(100):
                registry.increment_counter(f"counter_{worker_id}")
                registry.set_gauge(f"gauge_{worker_id}", float(i))
                time.sleep(0.001)  # Small delay to increase chance of race conditions

            results.append(f"worker_{worker_id}_done")

        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify results
        assert len(results) == 5
        for i in range(5):
            assert registry.get_counter(f"counter_{i}") == 100
            assert registry.get_gauge(f"gauge_{i}") == 99.0

    def test_metrics_cleanup(self):
        """Test automatic cleanup of old metric data."""
        registry = MetricsRegistry(max_history_size=10, retention_hours=0.001)  # Very short retention

        # Add some data points
        for i in range(5):
            registry.increment_counter("test_counter", tags={"index": str(i)})
            time.sleep(0.001)  # Small delay to create time separation

        # Force cleanup by adding more data
        time.sleep(0.01)  # Wait longer than retention period
        for i in range(10):
            registry.increment_counter("test_counter", tags={"new": str(i)})

        # Check that old data was cleaned up
        assert len(registry._metric_history["test_counter"]) <= 10


class TestAlertSystem:
    """Test the alerting and rule evaluation system."""

    def test_alert_rule_creation(self):
        """Test alert rule creation and validation."""
        rule = AlertRule(
            name="test_rule",
            metric_name="test_counter",
            condition="gt",
            threshold=10,
            severity=AlertSeverity.WARNING,
            description="Test alert rule"
        )

        assert rule.name == "test_rule"
        assert rule.metric_name == "test_counter"
        assert rule.condition == "gt"
        assert rule.threshold == 10
        assert rule.severity == AlertSeverity.WARNING

    def test_alert_rule_evaluation(self):
        """Test alert rule evaluation logic."""
        rule = AlertRule(
            name="test_rule",
            metric_name="test_counter",
            condition="gt",
            threshold=10,
            severity=AlertSeverity.WARNING
        )

        # Test conditions
        assert rule.evaluate(15) == True   # 15 > 10
        assert rule.evaluate(5) == False   # 5 > 10
        assert rule.evaluate(10) == False  # 10 > 10

        # Test different conditions
        lt_rule = AlertRule("lt_rule", "test", "lt", 10, AlertSeverity.WARNING)
        assert lt_rule.evaluate(5) == True
        assert lt_rule.evaluate(15) == False

        eq_rule = AlertRule("eq_rule", "test", "eq", 10, AlertSeverity.WARNING)
        assert eq_rule.evaluate(10) == True
        assert eq_rule.evaluate(5) == False

    def test_alert_lifecycle(self):
        """Test complete alert lifecycle."""
        registry = MetricsRegistry()

        # Add alert rule
        rule = AlertRule(
            name="high_error_rate",
            metric_name="error_rate_percent",
            condition="gt",
            threshold=20.0,
            severity=AlertSeverity.WARNING,
            cooldown_seconds=5
        )
        registry.add_alert_rule(rule)

        # Trigger alert
        registry.set_gauge("error_rate_percent", 25.0)
        alerts = registry.evaluate_alerts()

        assert len(alerts) == 1
        assert alerts[0].rule_name == "high_error_rate"
        assert alerts[0].severity == AlertSeverity.WARNING
        assert alerts[0].is_active == True

        # Check active alerts
        active = registry.get_active_alerts()
        assert len(active) == 1
        assert active[0].rule_name == "high_error_rate"

        # Resolve alert
        assert registry.resolve_alert("high_error_rate_high_error_rate") == True

        # Verify alert is resolved
        active_after = registry.get_active_alerts()
        assert len(active_after) == 0

    def test_alert_cooldown(self):
        """Test alert cooldown functionality."""
        registry = MetricsRegistry()

        rule = AlertRule(
            name="cooldown_test",
            metric_name="test_metric",
            condition="gt",
            threshold=5,
            severity=AlertSeverity.WARNING,
            cooldown_seconds=1  # 1 second cooldown
        )
        registry.add_alert_rule(rule)

        # Trigger alert
        registry.set_gauge("test_metric", 10)
        alerts1 = registry.evaluate_alerts()
        assert len(alerts1) == 1

        # Try to trigger again immediately (should be in cooldown)
        alerts2 = registry.evaluate_alerts()
        assert len(alerts2) == 0

        # Wait for cooldown and try again
        time.sleep(1.1)
        alerts3 = registry.evaluate_alerts()
        assert len(alerts3) == 1  # Should trigger again


class TestHealthMonitoring:
    """Test health check and monitoring functionality."""

    def test_health_check_registration(self):
        """Test registering health check functions."""
        registry = MetricsRegistry()

        def mock_health_check():
            return registry.HealthCheck(
                name="test_check",
                status=HealthStatus.HEALTHY,
                score=0.95,
                message="All systems operational",
                checked_at=time.time()
            )

        registry.register_health_check("test_component", mock_health_check)

        # Run health checks
        results = registry.run_health_checks()

        assert "test_component" in results
        check = results["test_component"]
        assert check.status == HealthStatus.HEALTHY
        assert check.score == 0.95
        assert "operational" in check.message

    def test_overall_health_score_calculation(self):
        """Test overall health score calculation."""
        registry = MetricsRegistry()

        # Register multiple health checks
        checks = [
            ("healthy_service", HealthStatus.HEALTHY, 1.0),
            ("degraded_service", HealthStatus.DEGRADED, 0.7),
            ("unhealthy_service", HealthStatus.UNHEALTHY, 0.3)
        ]

        for name, status, score in checks:
            def create_check(s=status, sc=score):
                def check():
                    return registry.HealthCheck(
                        name=name,
                        status=s,
                        score=sc,
                        message=f"{name} check",
                        checked_at=time.time()
                    )
                return check

            registry.register_health_check(name, create_check())

        # Run health checks
        registry.run_health_checks()

        # Calculate overall score
        overall_score = registry.get_overall_health_score()

        # Should be weighted average: (1.0 + 0.7 + 0.3) / 3 = 0.667
        expected_score = (1.0 + 0.7 + 0.3) / 3
        assert abs(overall_score - expected_score) < 0.001

    def test_health_check_failure_handling(self):
        """Test health check failure handling."""
        registry = MetricsRegistry()

        def failing_check():
            raise Exception("Service unavailable")

        registry.register_health_check("failing_service", failing_check)

        # Run health checks
        results = registry.run_health_checks()

        assert "failing_service" in results
        check = results["failing_service"]
        assert check.status == HealthStatus.UNHEALTHY
        assert check.score == 0.0
        assert "failed" in check.message.lower()


class TestMetricsConfiguration:
    """Test metrics configuration and validation."""

    def test_alert_rules_validation(self):
        """Test alert rules configuration validation."""
        # This should not raise an exception if configuration is valid
        validation_errors = validate_configuration()
        assert isinstance(validation_errors, list)

        # Check that our predefined rules are valid
        assert len(ALERT_RULES) > 0

        for rule in ALERT_RULES:
            assert rule.name
            assert rule.metric_name
            assert rule.condition in ["gt", "lt", "eq", "ne"]
            assert isinstance(rule.severity, AlertSeverity)

    def test_health_thresholds_configuration(self):
        """Test health check thresholds configuration."""
        thresholds = get_health_check_thresholds()

        required_keys = ["api_response_time", "error_rate", "success_rate", "data_freshness_hours"]
        for key in required_keys:
            assert key in thresholds
            assert "healthy" in thresholds[key]
            assert "degraded" in thresholds[key]
            assert "unhealthy" in thresholds[key]

    def test_configuration_initialization(self):
        """Test that configuration initializes properly."""
        from ai_content_pipeline.monitoring.metrics_config import initialize_alert_rules

        # Reset registry for clean test
        registry = get_registry()
        registry.reset()

        # Initialize alert rules
        initialize_alert_rules()

        # Check that rules were added
        assert len(registry._alert_rules) > 0

        # Verify specific rules exist
        assert "api_success_rate_warning" in registry._alert_rules
        assert "error_rate_warning" in registry._alert_rules


class TestMetricsIntegration:
    """Test integration of metrics across components."""

    def test_request_recording(self):
        """Test request recording convenience function."""
        registry = get_registry()
        registry.reset()

        # Record some requests
        record_request("api.generate_image", 1.2, success=True)
        record_request("api.generate_video", 3.4, success=False)

        # Check metrics
        assert registry.get_counter("api.requests_total") == 2
        assert registry.get_counter("api.requests_failed") == 1

        # Check timers
        timer_stats = registry.get_timer_stats("api.request_duration.api.generate_image")
        assert timer_stats["count"] == 1
        assert timer_stats["mean"] == 1.2

    def test_error_recording(self):
        """Test error recording functionality."""
        registry = get_registry()
        registry.reset()

        # Record errors
        record_error("api_error", "Invalid request parameters")
        record_error("processing_error", "Model timeout", tags={"model": "flux_dev"})

        # Check metrics
        assert registry.get_counter("errors_total") == 2
        assert registry.get_counter("errors.api_error") == 1
        assert registry.get_counter("errors.processing_error") == 1

    def test_metrics_snapshot(self):
        """Test complete metrics snapshot generation."""
        registry = get_registry()
        registry.reset()

        # Add some test data
        registry.increment_counter("test_counter", 5)
        registry.set_gauge("test_gauge", 42.0)
        registry.record_histogram("test_histogram", 10.0)
        registry.record_timer("test_timer", 2.5)

        # Get snapshot
        snapshot = registry.get_metrics_snapshot()

        # Verify structure
        assert "counters" in snapshot
        assert "gauges" in snapshot
        assert "histograms" in snapshot
        assert "timers" in snapshot
        assert "active_alerts" in snapshot
        assert "health_score" in snapshot
        assert "timestamp" in snapshot

        # Verify data
        assert snapshot["counters"]["test_counter"] == 5
        assert snapshot["gauges"]["test_gauge"] == 42.0
        assert snapshot["histograms"]["test_histogram"]["count"] == 1
        assert snapshot["timers"]["test_timer"]["count"] == 1


class TestCLIMonitoring:
    """Test CLI monitoring commands."""

    @patch('ai_content_pipeline.monitoring.metrics.get_registry')
    def test_show_metrics_command(self, mock_get_registry, capsys):
        """Test show-metrics CLI command."""
        mock_registry = Mock()
        mock_registry.get_metrics_snapshot.return_value = {
            "counters": {"test": 1},
            "gauges": {},
            "histograms": {},
            "timers": {},
            "active_alerts": 0,
            "health_score": 1.0,
            "total_collections": 10,
            "uptime_seconds": 3600,
            "timestamp": time.time()
        }
        mock_get_registry.return_value = mock_registry

        # Import and test the CLI function
        from ai_content_pipeline.__main__ import show_metrics

        # Create mock args
        mock_args = Mock()
        mock_args.json = False

        show_metrics(mock_args)

        captured = capsys.readouterr()
        assert "Current System Metrics" in captured.out
        assert "Uptime: 3600.0s" in captured.out
        assert "Active Alerts: 0" in captured.out

    @patch('ai_content_pipeline.monitoring.metrics.get_registry')
    def test_show_health_command(self, mock_get_registry, capsys):
        """Test show-health CLI command."""
        mock_registry = Mock()
        mock_health_check = Mock()
        mock_health_check.status = HealthStatus.HEALTHY
        mock_health_check.score = 0.95
        mock_health_check.message = "Service healthy"

        mock_registry.run_health_checks.return_value = {"test_service": mock_health_check}
        mock_registry.get_overall_health_score.return_value = 0.95
        mock_get_registry.return_value = mock_registry

        from ai_content_pipeline.__main__ import show_health

        mock_args = Mock()
        mock_args.json = False

        show_health(mock_args)

        captured = capsys.readouterr()
        assert "System Health Status" in captured.out
        assert "Overall Score: 0.950" in captured.out


class TestAPIEndpoints:
    """Test monitoring API endpoints."""

    def test_metrics_endpoint_structure(self):
        """Test metrics API endpoint response structure."""
        registry = MetricsRegistry()

        # Add some test data
        registry.increment_counter("api_calls", 10)
        registry.set_gauge("cpu_usage", 75.5)

        snapshot = registry.get_metrics_snapshot()

        # Verify required fields
        required_fields = ["counters", "gauges", "histograms", "timers",
                          "active_alerts", "health_score", "timestamp"]
        for field in required_fields:
            assert field in snapshot

    def test_health_endpoint_calculation(self):
        """Test health endpoint calculations."""
        registry = MetricsRegistry()

        # Register a health check
        def healthy_check():
            return registry.HealthCheck(
                name="test",
                status=HealthStatus.HEALTHY,
                score=0.9,
                message="OK",
                checked_at=time.time()
            )

        registry.register_health_check("test_component", healthy_check)
        registry.run_health_checks()

        score = registry.get_overall_health_score()
        assert score == 0.9

    def test_alerts_endpoint_data(self):
        """Test alerts endpoint data structure."""
        registry = MetricsRegistry()

        # Add an alert rule and trigger it
        rule = AlertRule("test_alert", "test_metric", "gt", 5, AlertSeverity.WARNING)
        registry.add_alert_rule(rule)
        registry.set_gauge("test_metric", 10)
        registry.evaluate_alerts()

        active_alerts = registry.get_active_alerts()
        alert_history = registry.get_alert_history()

        assert len(active_alerts) == 1
        assert len(alert_history) == 1
        assert active_alerts[0].rule_name == "test_alert"


# Performance and Load Testing
class TestPerformance:
    """Test performance characteristics under load."""

    def test_high_frequency_metrics(self):
        """Test metrics collection under high frequency."""
        registry = MetricsRegistry(max_history_size=1000)

        start_time = time.time()

        # Rapid metric collection
        for i in range(1000):
            registry.increment_counter("perf_test")
            registry.record_histogram("perf_histogram", float(i % 100))

        end_time = time.time()
        duration = end_time - start_time

        # Should complete in reasonable time (< 1 second)
        assert duration < 1.0

        # Verify data integrity
        assert registry.get_counter("perf_test") == 1000
        hist_stats = registry.get_histogram_stats("perf_histogram")
        assert hist_stats["count"] == 1000

    def test_concurrent_alert_evaluation(self):
        """Test alert evaluation under concurrent load."""
        registry = MetricsRegistry()

        # Add multiple alert rules
        for i in range(10):
            rule = AlertRule(f"rule_{i}", f"metric_{i}", "gt", i * 10, AlertSeverity.WARNING)
            registry.add_alert_rule(rule)

        results = []

        def evaluate_worker():
            """Worker to evaluate alerts concurrently."""
            for _ in range(100):
                alerts = registry.evaluate_alerts()
                results.append(len(alerts))

        # Start concurrent evaluation
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=evaluate_worker)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Should have completed without errors
        assert len(results) == 500  # 5 threads * 100 evaluations each


# Integration tests
class TestIntegration:
    """Test integration across the monitoring system."""

    def test_full_monitoring_workflow(self):
        """Test complete monitoring workflow from request to alert."""
        registry = get_registry()
        registry.reset()

        # 1. Initialize configuration
        from ai_content_pipeline.monitoring.metrics_config import initialize_alert_rules
        initialize_alert_rules()

        # 2. Simulate application activity
        record_request("api.generate_image", 1.5, success=True, tags={"model": "flux_dev"})
        record_request("api.generate_video", 2.0, success=False, tags={"model": "sora"})

        # 3. Add some errors
        for _ in range(25):  # Trigger error rate alert (>20%)
            record_error("api_error", "Rate limit exceeded")

        # 4. Evaluate alerts
        alerts = registry.evaluate_alerts()

        # 5. Check that alerts were triggered
        alert_names = [alert.rule_name for alert in alerts]
        assert "error_rate_warning" in alert_names or "error_rate_critical" in alert_names

        # 6. Check metrics snapshot
        snapshot = registry.get_metrics_snapshot()
        assert snapshot["counters"]["api.requests_total"] == 2
        assert snapshot["counters"]["errors_total"] == 25

    def test_health_monitoring_integration(self):
        """Test health monitoring integration."""
        registry = get_registry()
        registry.reset()

        # Register health checks
        def api_health_check():
            return registry.HealthCheck(
                name="api_service",
                status=HealthStatus.HEALTHY,
                score=0.95,
                message="API responding normally",
                checked_at=time.time(),
                response_time=0.1
            )

        def database_health_check():
            return registry.HealthCheck(
                name="database",
                status=HealthStatus.DEGRADED,
                score=0.6,
                message="High connection latency",
                checked_at=time.time(),
                response_time=2.5
            )

        registry.register_health_check("api", api_health_check)
        registry.register_health_check("database", database_health_check)

        # Run health checks
        results = registry.run_health_checks()

        # Verify results
        assert len(results) == 2
        assert results["api"].status == HealthStatus.HEALTHY
        assert results["database"].status == HealthStatus.DEGRADED

        # Check overall health score
        overall_score = registry.get_overall_health_score()
        expected_score = (0.95 + 0.6) / 2  # Average of both scores
        assert abs(overall_score - expected_score) < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])