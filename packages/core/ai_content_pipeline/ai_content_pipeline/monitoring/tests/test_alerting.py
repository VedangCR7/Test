"""
Unit tests for alerting system functionality.

Tests cover alert rules, alert evaluation, cooldown mechanisms,
and alert lifecycle management.
"""

import pytest
import time
from unittest.mock import patch

from ..metrics import MetricsRegistry, AlertRule, Alert, AlertSeverity


class TestAlertRuleValidation:
    """Test alert rule creation and validation."""

    def test_valid_alert_rule_creation(self):
        """Test creating alert rules with valid parameters."""
        rule = AlertRule(
            name="valid_rule",
            metric_name="test_metric",
            condition="gt",
            threshold=100,
            severity=AlertSeverity.WARNING,
            cooldown_seconds=300,
            description="Valid test rule",
        )

        assert rule.name == "valid_rule"
        assert rule.metric_name == "test_metric"
        assert rule.condition == "gt"
        assert rule.threshold == 100
        assert rule.severity == AlertSeverity.WARNING
        assert rule.cooldown_seconds == 300
        assert rule.description == "Valid test rule"
        assert rule.enabled is True

    def test_alert_rule_defaults(self):
        """Test alert rule default values."""
        rule = AlertRule(
            name="default_test",
            metric_name="test_metric",
            condition="lt",
            threshold=50,
            severity=AlertSeverity.ERROR,
        )

        assert rule.cooldown_seconds == 300  # Default 5 minutes
        assert rule.description == ""  # Default empty
        assert rule.enabled is True  # Default enabled

    def test_disabled_alert_rule(self):
        """Test disabled alert rule behavior."""
        rule = AlertRule(
            name="disabled_rule",
            metric_name="test_metric",
            condition="gt",
            threshold=100,
            severity=AlertSeverity.CRITICAL,
            enabled=False,
        )

        # Disabled rule should never evaluate to True
        assert rule.evaluate(200) is False
        assert rule.evaluate(50) is False

    @pytest.mark.parametrize(
        "condition,value,threshold,expected",
        [
            ("gt", 150, 100, True),  # 150 > 100
            ("gt", 50, 100, False),  # 50 > 100
            ("gt", 100, 100, False),  # 100 > 100
            ("lt", 50, 100, True),  # 50 < 100
            ("lt", 150, 100, False),  # 150 < 100
            ("lt", 100, 100, False),  # 100 < 100
            ("eq", 100, 100, True),  # 100 == 100
            ("eq", 50, 100, False),  # 50 == 100
            ("ne", 50, 100, True),  # 50 != 100
            ("ne", 100, 100, False),  # 100 != 100
        ],
    )
    def test_alert_rule_conditions(self, condition, value, threshold, expected):
        """Test all alert rule condition evaluations."""
        rule = AlertRule(
            name=f"{condition}_test",
            metric_name="test_metric",
            condition=condition,
            threshold=threshold,
            severity=AlertSeverity.INFO,
        )

        assert rule.evaluate(value) == expected

    def test_invalid_alert_condition(self):
        """Test handling of invalid alert conditions."""
        rule = AlertRule(
            name="invalid_condition",
            metric_name="test_metric",
            condition="invalid_op",
            threshold=100,
            severity=AlertSeverity.WARNING,
        )

        with patch("src.monitoring.metrics.logger") as mock_logger:
            result = rule.evaluate(150)
            assert result is False
            mock_logger.warning.assert_called_once_with(
                "Unknown alert condition: invalid_op"
            )


class TestAlertLifecycle:
    """Test alert creation, triggering, and resolution."""

    def test_alert_creation(self):
        """Test alert object creation and properties."""
        alert = Alert(
            rule_name="test_rule",
            severity=AlertSeverity.ERROR,
            message="Test alert message",
            value=150.0,
            threshold=100.0,
            triggered_at=1234567890.0,
            tags={"component": "test"},
        )

        assert alert.rule_name == "test_rule"
        assert alert.severity == AlertSeverity.ERROR
        assert alert.message == "Test alert message"
        assert alert.value == 150.0
        assert alert.threshold == 100.0
        assert alert.triggered_at == 1234567890.0
        assert alert.resolved_at is None
        assert alert.is_active is True
        assert alert.tags == {"component": "test"}

    def test_alert_resolution(self):
        """Test alert resolution functionality."""
        alert = Alert(
            rule_name="test_rule",
            severity=AlertSeverity.WARNING,
            message="Test message",
            value=200.0,
            threshold=150.0,
            triggered_at=time.time(),
        )

        assert alert.is_active is True
        assert alert.resolved_at is None

        # Resolve the alert
        resolved_time = time.time()
        alert.resolved_at = resolved_time

        assert alert.is_active is False
        assert alert.resolved_at == resolved_time

    def test_alert_cooldown_tracking(self):
        """Test alert cooldown period tracking."""
        current_time = time.time()
        cooldown_until = current_time + 60  # 1 minute cooldown

        alert = Alert(
            rule_name="cooldown_test",
            severity=AlertSeverity.INFO,
            message="Cooldown test",
            value=50.0,
            threshold=25.0,
            triggered_at=current_time,
            cooldown_until=cooldown_until,
        )

        # Test before cooldown expires
        assert alert.is_in_cooldown is True

        # Simulate cooldown expiration
        alert.cooldown_until = current_time - 1
        assert alert.is_in_cooldown is False


class TestRegistryAlertIntegration:
    """Test alert integration with MetricsRegistry."""

    def test_add_alert_rule(self):
        """Test adding alert rules to registry."""
        registry = MetricsRegistry()

        rule = AlertRule(
            name="registry_test",
            metric_name="test_counter",
            condition="gt",
            threshold=10,
            severity=AlertSeverity.WARNING,
        )

        registry.add_alert_rule(rule)
        assert "registry_test" in registry._alert_rules
        assert registry._alert_rules["registry_test"] == rule

    def test_alert_evaluation_counter(self):
        """Test alert evaluation with counter metrics."""
        registry = MetricsRegistry()

        # Add alert rule
        rule = AlertRule(
            name="counter_alert",
            metric_name="test_counter",
            condition="gt",
            threshold=5,
            severity=AlertSeverity.ERROR,
        )
        registry.add_alert_rule(rule)

        # Counter below threshold - no alert
        registry.increment_counter("test_counter", 3)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 0

        # Counter above threshold - alert triggered
        registry.increment_counter("test_counter", 3)  # Total: 6
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1
        assert alerts[0].rule_name == "counter_alert"
        assert alerts[0].severity == AlertSeverity.ERROR
        assert alerts[0].value == 6
        assert alerts[0].threshold == 5

    def test_alert_evaluation_gauge(self):
        """Test alert evaluation with gauge metrics."""
        registry = MetricsRegistry()

        rule = AlertRule(
            name="gauge_alert",
            metric_name="test_gauge",
            condition="lt",
            threshold=50,
            severity=AlertSeverity.CRITICAL,
        )
        registry.add_alert_rule(rule)

        # Gauge above threshold - no alert
        registry.set_gauge("test_gauge", 75)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 0

        # Gauge below threshold - alert triggered
        registry.set_gauge("test_gauge", 25)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1
        assert alerts[0].rule_name == "gauge_alert"
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_alert_evaluation_histogram(self):
        """Test alert evaluation with histogram mean."""
        registry = MetricsRegistry()

        rule = AlertRule(
            name="histogram_alert",
            metric_name="test_histogram",
            condition="gt",
            threshold=10,
            severity=AlertSeverity.WARNING,
        )
        registry.add_alert_rule(rule)

        # Add values with mean below threshold
        for value in [5, 8, 12]:  # Mean = 8.33
            registry.record_histogram("test_histogram", value)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 0

        # Add high value to push mean above threshold
        registry.record_histogram("test_histogram", 50)  # New mean > 10
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1
        assert alerts[0].rule_name == "histogram_alert"

    def test_multiple_alert_rules(self):
        """Test multiple alert rules evaluation."""
        registry = MetricsRegistry()

        # Add multiple rules
        rules = [
            AlertRule("rule1", "counter1", "gt", 5, AlertSeverity.INFO),
            AlertRule("rule2", "counter2", "gt", 10, AlertSeverity.WARNING),
            AlertRule("rule3", "gauge1", "lt", 20, AlertSeverity.ERROR),
        ]

        for rule in rules:
            registry.add_alert_rule(rule)

        # Trigger first rule only
        registry.increment_counter("counter1", 10)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1
        assert alerts[0].rule_name == "rule1"

        # Trigger second rule
        registry.increment_counter("counter2", 15)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1  # Second rule triggered
        assert alerts[0].rule_name == "rule2"

        # Trigger third rule
        registry.set_gauge("gauge1", 10)
        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1  # Third rule triggered
        assert alerts[0].rule_name == "rule3"

    def test_alert_deduplication(self):
        """Test that same alert doesn't trigger multiple times."""
        registry = MetricsRegistry()

        rule = AlertRule(
            name="dedup_test",
            metric_name="test_counter",
            condition="gt",
            threshold=5,
            severity=AlertSeverity.WARNING,
        )
        registry.add_alert_rule(rule)

        # First trigger
        registry.increment_counter("test_counter", 10)
        alerts1 = registry.evaluate_alerts()
        assert len(alerts1) == 1

        # Second evaluation with same high value - should not trigger again
        registry.increment_counter("test_counter", 1)  # Still > 5
        alerts2 = registry.evaluate_alerts()
        assert len(alerts2) == 0  # No new alerts

        # Reset counter below threshold, then trigger again
        registry.reset()
        registry.increment_counter("test_counter", 10)
        alerts3 = registry.evaluate_alerts()
        assert len(alerts3) == 1  # New alert after reset


class TestAlertCooldown:
    """Test alert cooldown functionality."""

    def test_alert_cooldown_prevents_retrigger(self):
        """Test that cooldown prevents alert retriggering."""
        registry = MetricsRegistry()

        rule = AlertRule(
            name="cooldown_rule",
            metric_name="test_counter",
            condition="gt",
            threshold=5,
            severity=AlertSeverity.WARNING,
            cooldown_seconds=2,  # 2 second cooldown
        )
        registry.add_alert_rule(rule)

        # Trigger alert
        registry.increment_counter("test_counter", 10)
        alerts1 = registry.evaluate_alerts()
        assert len(alerts1) == 1

        # Immediate re-evaluation should not trigger (in cooldown)
        registry.increment_counter("test_counter", 5)  # Even higher value
        alerts2 = registry.evaluate_alerts()
        assert len(alerts2) == 0

        # Wait for cooldown to expire
        time.sleep(2.1)

        # Should be able to trigger again
        alerts3 = registry.evaluate_alerts()
        assert len(alerts3) == 1

    def test_cooldown_with_different_rules(self):
        """Test cooldown works independently for different rules."""
        registry = MetricsRegistry()

        rule1 = AlertRule(
            name="rule1",
            metric_name="counter1",
            condition="gt",
            threshold=5,
            severity=AlertSeverity.INFO,
            cooldown_seconds=1,
        )
        rule2 = AlertRule(
            name="rule2",
            metric_name="counter2",
            condition="gt",
            threshold=10,
            severity=AlertSeverity.WARNING,
            cooldown_seconds=3,  # Different cooldown
        )

        registry.add_alert_rule(rule1)
        registry.add_alert_rule(rule2)

        # Trigger both rules
        registry.increment_counter("counter1", 10)
        registry.increment_counter("counter2", 15)
        alerts1 = registry.evaluate_alerts()
        assert len(alerts1) == 2  # Both should trigger

        # Immediate re-evaluation
        alerts2 = registry.evaluate_alerts()
        assert len(alerts2) == 0  # Both in cooldown

        # Wait for rule1 cooldown to expire (1 second)
        time.sleep(1.1)
        alerts3 = registry.evaluate_alerts()
        assert len(alerts3) == 1  # rule1 should trigger
        assert alerts3[0].rule_name == "rule1"

        # Wait for rule2 cooldown to expire (additional 2 seconds)
        time.sleep(2.1)
        alerts4 = registry.evaluate_alerts()
        assert len(alerts4) == 1  # rule2 should trigger
        assert alerts4[0].rule_name == "rule2"


class TestAlertPersistence:
    """Test alert history and persistence."""

    def test_alert_history_tracking(self):
        """Test that alerts are tracked in history."""
        registry = MetricsRegistry()

        rule = AlertRule("history_test", "test_counter", "gt", 5, AlertSeverity.INFO)
        registry.add_alert_rule(rule)

        # Trigger multiple alerts over time
        for i in range(3):
            registry.increment_counter("test_counter", 10)
            registry.evaluate_alerts()
            time.sleep(0.01)  # Ensure different timestamps

        history = registry.get_alert_history()
        assert len(history) == 3

        # Verify history contains expected alerts
        for alert in history:
            assert alert.rule_name == "history_test"
            assert alert.severity == AlertSeverity.INFO
            assert alert.is_active is True  # Not resolved yet

    def test_alert_history_limit(self):
        """Test alert history respects limit parameter."""
        registry = MetricsRegistry()

        # Add some alerts to history
        for i in range(5):
            alert = Alert(
                rule_name=f"test_rule_{i}",
                severity=AlertSeverity.WARNING,
                message=f"Test alert {i}",
                value=float(i),
                threshold=0.0,
                triggered_at=time.time() + i,
            )
            registry._alert_history.append(alert)

        # Test default history (should return all)
        history = registry.get_alert_history()
        assert len(history) == 5

        # Test limited history
        limited_history = registry.get_alert_history(limit=3)
        assert len(limited_history) == 3

        # Test zero limit
        empty_history = registry.get_alert_history(limit=0)
        assert len(empty_history) == 0

    def test_resolved_alert_history(self):
        """Test that resolved alerts appear in history."""
        registry = MetricsRegistry()

        # Create and resolve an alert
        alert = Alert(
            rule_name="resolved_test",
            severity=AlertSeverity.ERROR,
            message="Test resolved alert",
            value=100.0,
            threshold=50.0,
            triggered_at=time.time(),
        )

        registry._active_alerts["test_key"] = alert

        # Resolve the alert
        assert registry.resolve_alert("test_key") is True

        # Check that it's in history but not active
        assert len(registry.get_active_alerts()) == 0
        history = registry.get_alert_history()
        assert len(history) >= 1

        # Find our resolved alert
        resolved_alert = None
        for h_alert in history:
            if h_alert.rule_name == "resolved_test":
                resolved_alert = h_alert
                break

        assert resolved_alert is not None
        assert resolved_alert.resolved_at is not None
        assert resolved_alert.is_active is False


class TestAlertTags:
    """Test alert tagging functionality."""

    def test_alert_tags_from_rule(self):
        """Test that alerts inherit tags from metric context."""
        registry = MetricsRegistry()

        rule = AlertRule(
            name="tagged_rule",
            metric_name="tagged_counter",
            condition="gt",
            threshold=5,
            severity=AlertSeverity.INFO,
        )
        registry.add_alert_rule(rule)

        # Increment counter with tags
        registry.increment_counter(
            "tagged_counter", 10, tags={"service": "test", "env": "dev"}
        )

        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1

        alert = alerts[0]
        assert "service" in alert.tags
        assert "env" in alert.tags
        assert alert.tags["service"] == "test"
        assert alert.tags["env"] == "dev"

    def test_alert_tags_merge(self):
        """Test that alert tags merge correctly."""
        registry = MetricsRegistry()

        rule = AlertRule(
            name="merge_test",
            metric_name="merge_counter",
            condition="gt",
            threshold=3,
            severity=AlertSeverity.WARNING,
        )
        registry.add_alert_rule(rule)

        # The rule evaluation should add its own tags
        registry.increment_counter("merge_counter", 5, tags={"user_tag": "value"})

        alerts = registry.evaluate_alerts()
        assert len(alerts) == 1

        alert = alerts[0]
        # Should have both metric tags and rule-generated tags
        assert "user_tag" in alert.tags
        assert "metric" in alert.tags
        assert alert.tags["user_tag"] == "value"
        assert alert.tags["metric"] == "merge_counter"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
