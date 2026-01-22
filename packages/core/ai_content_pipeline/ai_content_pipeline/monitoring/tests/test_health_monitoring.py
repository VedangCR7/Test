"""
Unit tests for health monitoring functionality.

Tests cover health check registration, execution, scoring,
and integration with the overall monitoring system.
"""

import pytest
import time
from unittest.mock import Mock, patch

from ..metrics import MetricsRegistry, HealthStatus, get_registry
from ..health_checks import (
    check_api_endpoints,
    check_filesystem,
    check_system_resources,
    check_external_services,
    check_pipeline_performance,
    register_default_health_checks,
)


class TestHealthCheckBasics:
    """Test basic health check functionality."""

    def test_health_check_creation(self):
        """Test creating health check results."""
        registry = MetricsRegistry()

        check = registry.HealthCheck(
            name="test_check",
            status=HealthStatus.HEALTHY,
            score=0.95,
            message="Test check passed",
            checked_at=time.time(),
            response_time=0.1,
            details={"extra": "info"},
        )

        assert check.name == "test_check"
        assert check.status == HealthStatus.HEALTHY
        assert check.score == 0.95
        assert check.message == "Test check passed"
        assert check.response_time == 0.1
        assert check.details == {"extra": "info"}
        assert isinstance(check.checked_at, (int, float))

    def test_health_status_enum_values(self):
        """Test health status enum has expected values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"

        # Test all enum values are strings
        for status in HealthStatus:
            assert isinstance(status.value, str)

    def test_health_check_scoring_bounds(self):
        """Test health check scoring is within valid bounds."""
        registry = MetricsRegistry()

        # Test valid scores
        for score in [0.0, 0.5, 1.0]:
            check = registry.HealthCheck(
                name=f"score_{score}",
                status=HealthStatus.HEALTHY,
                score=score,
                message="Test",
                checked_at=time.time(),
            )
            assert 0.0 <= check.score <= 1.0

        # Test invalid scores are clamped (this would be application logic)
        # Health checks should validate their own scores


class TestHealthCheckRegistration:
    """Test health check registration and management."""

    def test_register_health_check(self):
        """Test registering health check functions."""
        registry = MetricsRegistry()

        def mock_check():
            return registry.HealthCheck(
                name="mock_check",
                status=HealthStatus.HEALTHY,
                score=1.0,
                message="Mock check",
                checked_at=time.time(),
            )

        registry.register_health_check("test_check", mock_check)

        assert "test_check" in registry._health_check_functions
        assert registry._health_check_functions["test_check"] == mock_check

    def test_register_duplicate_health_check(self):
        """Test registering duplicate health check names."""
        registry = MetricsRegistry()

        def check1():
            return registry.HealthCheck(
                "dup", HealthStatus.HEALTHY, 1.0, "Check 1", time.time()
            )

        def check2():
            return registry.HealthCheck(
                "dup", HealthStatus.HEALTHY, 1.0, "Check 2", time.time()
            )

        # First registration should work
        registry.register_health_check("duplicate_check", check1)
        assert registry._health_check_functions["duplicate_check"] == check1

        # Second registration should overwrite
        registry.register_health_check("duplicate_check", check2)
        assert registry._health_check_functions["duplicate_check"] == check2

    def test_run_health_checks_empty_registry(self):
        """Test running health checks when none are registered."""
        registry = MetricsRegistry()

        results = registry.run_health_checks()
        assert results == {}
        assert registry.get_overall_health_score() == 1.0  # Default healthy

    def test_run_health_checks_with_registered_checks(self):
        """Test running health checks with registered functions."""
        registry = MetricsRegistry()

        call_counts = {"check1": 0, "check2": 0}

        def create_check(name, status, score):
            def check():
                call_counts[name] += 1
                return registry.HealthCheck(
                    name=name,
                    status=status,
                    score=score,
                    message=f"{name} result",
                    checked_at=time.time(),
                    response_time=0.05,
                )

            return check

        # Register multiple checks
        registry.register_health_check(
            "check1", create_check("check1", HealthStatus.HEALTHY, 1.0)
        )
        registry.register_health_check(
            "check2", create_check("check2", HealthStatus.DEGRADED, 0.7)
        )

        results = registry.run_health_checks()

        # Verify results
        assert len(results) == 2
        assert results["check1"].status == HealthStatus.HEALTHY
        assert results["check1"].score == 1.0
        assert results["check2"].status == HealthStatus.DEGRADED
        assert results["check2"].score == 0.7

        # Verify calls were made
        assert call_counts["check1"] == 1
        assert call_counts["check2"] == 1

        # Verify stored results
        assert "check1" in registry._health_checks
        assert "check2" in registry._health_checks


class TestHealthCheckErrorHandling:
    """Test health check error handling."""

    def test_health_check_exception_handling(self):
        """Test that health check exceptions are handled gracefully."""
        registry = MetricsRegistry()

        def failing_check():
            raise Exception("Test failure")

        registry.register_health_check("failing_check", failing_check)

        results = registry.run_health_checks()

        assert "failing_check" in results
        check = results["failing_check"]

        assert check.status == HealthStatus.UNHEALTHY
        assert check.score == 0.0
        assert "Test failure" in check.message
        assert check.response_time >= 0  # Should still have response time

    def test_health_check_timeout_simulation(self):
        """Test health check behavior with timeouts."""
        registry = MetricsRegistry()

        def slow_check():
            time.sleep(0.1)  # Simulate slow operation
            return registry.HealthCheck(
                name="slow_check",
                status=HealthStatus.HEALTHY,
                score=0.9,
                message="Slow but healthy",
                checked_at=time.time(),
            )

        registry.register_health_check("slow_check", slow_check)

        start_time = time.time()
        results = registry.run_health_checks()
        end_time = time.time()

        assert "slow_check" in results
        check = results["slow_check"]

        # Should have recorded response time
        assert check.response_time >= 0.1
        assert check.response_time <= end_time - start_time + 0.01  # Small tolerance

    def test_mixed_health_check_results(self):
        """Test handling mixed healthy and unhealthy check results."""
        registry = MetricsRegistry()

        checks = [
            ("healthy", HealthStatus.HEALTHY, 1.0),
            ("degraded", HealthStatus.DEGRADED, 0.6),
            ("unhealthy", HealthStatus.UNHEALTHY, 0.2),
            ("failing", None, None),  # Will raise exception
        ]

        for name, status, score in checks:
            if name == "failing":

                def failing_check():
                    raise Exception("Simulated failure")

                registry.register_health_check(name, failing_check)
            else:

                def create_check(check_name, check_status, check_score):
                    def check():
                        return registry.HealthCheck(
                            name=check_name,
                            status=check_status,
                            score=check_score,
                            message=f"{check_name} check",
                            checked_at=time.time(),
                        )

                    return check

                registry.register_health_check(name, create_check(name, status, score))

        results = registry.run_health_checks()

        assert len(results) == 4

        # Check individual results
        assert results["healthy"].status == HealthStatus.HEALTHY
        assert results["healthy"].score == 1.0

        assert results["degraded"].status == HealthStatus.DEGRADED
        assert results["degraded"].score == 0.6

        assert results["unhealthy"].status == HealthStatus.UNHEALTHY
        assert results["unhealthy"].score == 0.2

        assert results["failing"].status == HealthStatus.UNHEALTHY
        assert results["failing"].score == 0.0


class TestOverallHealthScore:
    """Test overall health score calculation."""

    def test_overall_health_score_empty_checks(self):
        """Test overall health score with no health checks."""
        registry = MetricsRegistry()

        score = registry.get_overall_health_score()
        assert score == 1.0  # Default healthy when no checks

    def test_overall_health_score_single_check(self):
        """Test overall health score with single check."""
        registry = MetricsRegistry()

        # Add single healthy check
        registry._health_checks["single"] = registry.HealthCheck(
            name="single",
            status=HealthStatus.HEALTHY,
            score=0.8,
            message="Single check",
            checked_at=time.time(),
        )

        score = registry.get_overall_health_score()
        assert score == 0.8

    def test_overall_health_score_multiple_checks(self):
        """Test overall health score with multiple checks."""
        registry = MetricsRegistry()

        checks = [
            ("check1", HealthStatus.HEALTHY, 1.0),
            ("check2", HealthStatus.DEGRADED, 0.7),
            ("check3", HealthStatus.HEALTHY, 0.9),
        ]

        for name, status, score in checks:
            registry._health_checks[name] = registry.HealthCheck(
                name=name,
                status=status,
                score=score,
                message=f"{name} check",
                checked_at=time.time(),
            )

        overall_score = registry.get_overall_health_score()
        expected_score = (1.0 + 0.7 + 0.9) / 3  # Simple average
        assert abs(overall_score - expected_score) < 0.001

    def test_overall_health_score_weighting(self):
        """Test health score weighting for different severity levels."""
        registry = MetricsRegistry()

        # Add checks with different severity levels
        checks = [
            ("critical", HealthStatus.UNHEALTHY, 0.3, True),  # Critical gets 2x weight
            ("warning", HealthStatus.DEGRADED, 0.7, False),  # Normal gets 1x weight
            ("info", HealthStatus.HEALTHY, 1.0, False),  # Normal gets 1x weight
        ]

        total_weighted_score = 0
        total_weight = 0

        for name, status, score, is_critical in checks:
            weight = 2.0 if is_critical else 1.0
            registry._health_checks[name] = registry.HealthCheck(
                name=name,
                status=status,
                score=score,
                message=f"{name} check",
                checked_at=time.time(),
            )
            total_weighted_score += score * weight
            total_weight += weight

        overall_score = registry.get_overall_health_score()
        expected_score = total_weighted_score / total_weight

        assert abs(overall_score - expected_score) < 0.001


class TestFilesystemHealthCheck:
    """Test filesystem health monitoring."""

    @patch("src.health_checks.psutil.disk_usage")
    @patch("src.health_checks.Path")
    def test_filesystem_check_healthy(self, mock_path, mock_disk_usage):
        """Test filesystem check with healthy disk space."""
        # Mock disk usage (80% free)
        mock_disk_usage.return_value.free = 800
        mock_disk_usage.return_value.total = 1000

        # Mock path operations
        mock_cwd = Mock()
        mock_cwd.exists.return_value = True
        mock_path.cwd.return_value = mock_cwd

        result = check_filesystem()

        assert result.status == HealthStatus.HEALTHY
        assert result.score == 1.0
        assert "80.0%" in result.message
        assert result.details["available_percent"] == 80.0

    @patch("src.health_checks.psutil.disk_usage")
    @patch("src.health_checks.Path")
    def test_filesystem_check_degraded(self, mock_path, mock_disk_usage):
        """Test filesystem check with degraded disk space."""
        # Mock disk usage (8% free - warning level)
        mock_disk_usage.return_value.free = 80
        mock_disk_usage.return_value.total = 1000

        mock_cwd = Mock()
        mock_cwd.exists.return_value = True
        mock_path.cwd.return_value = mock_cwd

        result = check_filesystem()

        assert result.status == HealthStatus.DEGRADED
        assert result.score == 0.5  # Degraded score
        assert "8.0%" in result.message

    @patch("src.health_checks.psutil.disk_usage")
    @patch("src.health_checks.Path")
    def test_filesystem_check_unhealthy(self, mock_path, mock_disk_usage):
        """Test filesystem check with critically low disk space."""
        # Mock disk usage (3% free - critical level)
        mock_disk_usage.return_value.free = 30
        mock_disk_usage.return_value.total = 1000

        mock_cwd = Mock()
        mock_cwd.exists.return_value = True
        mock_path.cwd.return_value = mock_cwd

        result = check_filesystem()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.score == 0.2  # Unhealthy score
        assert "3.0%" in result.message

    @patch("src.health_checks.Path")
    def test_filesystem_check_missing_directory(self, mock_path):
        """Test filesystem check when current directory doesn't exist."""
        mock_cwd = Mock()
        mock_cwd.exists.return_value = False
        mock_path.cwd.return_value = mock_cwd

        result = check_filesystem()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.score == 0.0
        assert "does not exist" in result.message


class TestSystemResourceHealthCheck:
    """Test system resource health monitoring."""

    @patch("src.health_checks.psutil.cpu_percent")
    @patch("src.health_checks.psutil.virtual_memory")
    def test_system_resources_healthy(self, mock_memory, mock_cpu):
        """Test system resources check with healthy values."""
        mock_cpu.return_value = 30.0  # 30% CPU usage
        mock_memory.percent = 40.0  # 40% memory usage
        mock_memory.used = 4 * 1024**3  # 4GB used
        mock_memory.total = 16 * 1024**3  # 16GB total

        result = check_system_resources()

        assert result.status == HealthStatus.HEALTHY
        assert result.score > 0.8  # Should be healthy score
        assert "30.0%" in result.message
        assert result.details["cpu_percent"] == 30.0
        assert result.details["memory_percent"] == 40.0

    @patch("src.health_checks.psutil.cpu_percent")
    @patch("src.health_checks.psutil.virtual_memory")
    def test_system_resources_degraded(self, mock_memory, mock_cpu):
        """Test system resources check with degraded values."""
        mock_cpu.return_value = 75.0  # 75% CPU usage
        mock_memory.percent = 75.0  # 75% memory usage

        result = check_system_resources()

        assert result.status == HealthStatus.DEGRADED
        assert "75.0%" in result.message

    @patch("src.health_checks.psutil.cpu_percent")
    @patch("src.health_checks.psutil.virtual_memory")
    def test_system_resources_unhealthy(self, mock_memory, mock_cpu):
        """Test system resources check with unhealthy values."""
        mock_cpu.return_value = 95.0  # 95% CPU usage
        mock_memory.percent = 95.0  # 95% memory usage

        result = check_system_resources()

        assert result.status == HealthStatus.UNHEALTHY
        assert "95.0%" in result.message

    @patch("src.health_checks.psutil.cpu_percent")
    def test_system_resources_cpu_error(self, mock_cpu):
        """Test system resources check when CPU monitoring fails."""
        mock_cpu.side_effect = Exception("CPU monitoring failed")

        result = check_system_resources()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.score == 0.0
        assert "CPU monitoring failed" in result.message


class TestAPIEndpointHealthCheck:
    """Test API endpoint health monitoring."""

    def test_api_endpoints_check_with_metrics(self):
        """Test API endpoints check with existing metrics."""
        registry = get_registry()

        # Add some test metrics
        registry.increment_counter("api.requests_total", 100)
        registry.set_gauge("api.success_rate", 0.95)

        result = check_api_endpoints()

        assert result.status == HealthStatus.HEALTHY
        assert result.score == 1.0
        assert "responding normally" in result.message
        assert result.details["metrics_collections"] == 100

    def test_api_endpoints_check_no_recent_data(self):
        """Test API endpoints check with no recent metrics."""
        registry = get_registry()
        registry.reset()  # Clear all metrics

        result = check_api_endpoints()

        assert result.status == HealthStatus.DEGRADED
        assert result.score == 0.5
        assert "limited metrics data" in result.message

    def test_api_endpoints_check_exception(self):
        """Test API endpoints check when registry access fails."""
        with patch("src.health_checks.get_registry") as mock_get_registry:
            mock_get_registry.side_effect = Exception("Registry access failed")

            result = check_api_endpoints()

            assert result.status == HealthStatus.UNHEALTHY
            assert result.score == 0.0
            assert "Registry access failed" in result.message


class TestExternalServicesHealthCheck:
    """Test external services health monitoring."""

    @patch("src.health_checks.requests.get")
    def test_external_services_all_healthy(self, mock_get):
        """Test external services check when all services are healthy."""
        # Mock successful responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # Mock environment variables
        with patch.dict(
            "os.environ", {"FAL_KEY": "test_key", "ELEVENLABS_API_KEY": "test_key"}
        ):
            result = check_external_services()

        assert result.status == HealthStatus.HEALTHY
        assert result.score == 1.0
        assert "All 2 external services reachable" in result.message

    @patch("src.health_checks.requests.get")
    def test_external_services_partial_failure(self, mock_get):
        """Test external services check with partial failures."""

        # Mock one success, one failure
        def mock_response_side_effect(*args, **kwargs):
            mock_resp = Mock()
            if "fal.ai" in args[0]:
                mock_resp.status_code = 200
            else:
                mock_resp.status_code = 500
            return mock_resp

        mock_get.side_effect = mock_response_side_effect

        with patch.dict(
            "os.environ", {"FAL_KEY": "test_key", "ELEVENLABS_API_KEY": "test_key"}
        ):
            result = check_external_services()

        assert result.status == HealthStatus.DEGRADED
        assert result.score == 0.5  # 1/2 services healthy
        assert "Some external services unreachable" in result.message

    @patch("src.health_checks.requests.get")
    def test_external_services_all_failed(self, mock_get):
        """Test external services check when all services fail."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        with patch.dict("os.environ", {"FAL_KEY": "test_key"}):
            result = check_external_services()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.score == 0.0
        assert "Multiple external services unreachable" in result.message

    def test_external_services_no_configured(self):
        """Test external services check with no services configured."""
        with patch.dict("os.environ", {}, clear=True):
            result = check_external_services()

        assert result.status == HealthStatus.HEALTHY
        assert result.score == 1.0
        assert "No external services configured" in result.message


class TestPipelinePerformanceHealthCheck:
    """Test pipeline performance health monitoring."""

    def test_pipeline_performance_healthy(self):
        """Test pipeline performance check with healthy metrics."""
        registry = get_registry()

        # Set up healthy metrics
        registry._counters["api.requests_total"] = 1000
        registry._counters["api.requests_failed"] = 10  # 1% failure rate

        # Mock timer stats for healthy performance
        with patch.object(registry, "get_timer_stats") as mock_timer:
            mock_timer.return_value = {"mean": 0.5, "p95": 2.0, "p99": 5.0}

            result = check_pipeline_performance()

        assert result.status == HealthStatus.HEALTHY
        assert result.score == 1.0
        assert "95.0%" in result.message

    def test_pipeline_performance_degraded(self):
        """Test pipeline performance check with degraded metrics."""
        registry = get_registry()

        # Set up degraded metrics (higher failure rate, slower response)
        registry._counters["api.requests_total"] = 1000
        registry._counters["api.requests_failed"] = 200  # 20% failure rate

        with patch.object(registry, "get_timer_stats") as mock_timer:
            mock_timer.return_value = {"mean": 2.0, "p95": 8.0, "p99": 15.0}

            result = check_pipeline_performance()

        assert result.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert result.score < 1.0

    def test_pipeline_performance_no_requests(self):
        """Test pipeline performance check with no requests."""
        registry = get_registry()
        registry.reset()

        result = check_pipeline_performance()

        assert result.status == HealthStatus.HEALTHY
        assert result.score == 1.0
        assert "No requests processed yet" in result.message


class TestDefaultHealthCheckRegistration:
    """Test default health check registration."""

    def test_register_default_health_checks(self):
        """Test that default health checks are registered."""
        registry = get_registry()

        # Count initial checks
        initial_count = len(registry._health_check_functions)

        register_default_health_checks()

        # Should have added health checks
        assert len(registry._health_check_functions) > initial_count

        # Check that expected checks are registered
        expected_checks = [
            "api_endpoints",
            "filesystem",
            "system_resources",
            "external_services",
            "pipeline_performance",
        ]

        for check_name in expected_checks:
            assert check_name in registry._health_check_functions
            assert callable(registry._health_check_functions[check_name])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
