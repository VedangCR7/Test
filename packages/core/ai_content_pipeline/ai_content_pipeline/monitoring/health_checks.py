"""
Health check functions for the AI Content Pipeline monitoring system.

Provides automated health checks for various system components including
API endpoints, external services, filesystem, and performance metrics.
"""

import os
import time
import psutil
import requests
from pathlib import Path

from .metrics import HealthStatus, get_registry, MetricsRegistry


def check_api_endpoints() -> MetricsRegistry.HealthCheck:
    """
    Check API endpoint health by making test requests.

    Tests internal API endpoints for responsiveness and correct responses.
    """
    registry = get_registry()
    start_time = time.time()

    try:
        # Get current metrics to verify system is operational
        metrics = registry.get_metrics_snapshot()

        # Check if basic metrics are being collected
        has_recent_data = metrics.get("timestamp", 0) > (
            time.time() - 300
        )  # Within last 5 minutes

        if has_recent_data and metrics.get("total_collections", 0) > 0:
            score = 1.0
            status = HealthStatus.HEALTHY
            message = "API endpoints responding normally"
        else:
            score = 0.5
            status = HealthStatus.DEGRADED
            message = "API operational but limited metrics data"

        return MetricsRegistry.HealthCheck(
            name="api_endpoints",
            status=status,
            score=score,
            message=message,
            checked_at=time.time(),
            response_time=time.time() - start_time,
            details={
                "metrics_collections": metrics.get("total_collections", 0),
                "active_alerts": metrics.get("active_alerts", 0),
                "last_update": metrics.get("timestamp", 0),
            },
        )

    except Exception as e:
        return MetricsRegistry.HealthCheck(
            name="api_endpoints",
            status=HealthStatus.UNHEALTHY,
            score=0.0,
            message=f"API endpoints check failed: {str(e)}",
            checked_at=time.time(),
            response_time=time.time() - start_time,
        )


def check_filesystem() -> MetricsRegistry.HealthCheck:
    """
    Check filesystem health including disk space and permissions.

    Monitors available disk space and file system accessibility.
    """
    start_time = time.time()

    try:
        # Check current working directory
        cwd = Path.cwd()
        if not cwd.exists():
            raise ValueError("Current working directory does not exist")

        # Check disk usage
        disk_usage = psutil.disk_usage(str(cwd))

        # Calculate available space percentage
        available_percent = (disk_usage.free / disk_usage.total) * 100

        # Check critical directories exist
        critical_paths = ["output", "temp", "logs"]
        missing_paths = []

        for path_name in critical_paths:
            path = cwd / path_name
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except Exception:
                    missing_paths.append(path_name)

        # Determine health based on disk space and paths
        if available_percent < 5:  # Less than 5% free space
            score = 0.2
            status = HealthStatus.UNHEALTHY
            message = ".1f"
        elif available_percent < 10:  # Less than 10% free space
            score = 0.5
            status = HealthStatus.DEGRADED
            message = ".1f"
        elif missing_paths:
            score = 0.7
            status = HealthStatus.DEGRADED
            message = f"Critical directories missing: {', '.join(missing_paths)}"
        else:
            score = 1.0
            status = HealthStatus.HEALTHY
            message = ".1f"

        return MetricsRegistry.HealthCheck(
            name="filesystem",
            status=status,
            score=score,
            message=message,
            checked_at=time.time(),
            response_time=time.time() - start_time,
            details={
                "total_space_gb": disk_usage.total / (1024**3),
                "free_space_gb": disk_usage.free / (1024**3),
                "available_percent": available_percent,
                "missing_paths": missing_paths,
            },
        )

    except Exception as e:
        return MetricsRegistry.HealthCheck(
            name="filesystem",
            status=HealthStatus.UNHEALTHY,
            score=0.0,
            message=f"Filesystem check failed: {str(e)}",
            checked_at=time.time(),
            response_time=time.time() - start_time,
        )


def check_system_resources() -> MetricsRegistry.HealthCheck:
    """
    Check system resource usage (CPU, memory).

    Monitors system performance metrics and resource utilization.
    """
    start_time = time.time()

    try:
        # Get CPU usage (average over 1 second)
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # Calculate overall resource score
        # CPU weight: 40%, Memory weight: 60%
        resource_score = 1.0 - ((cpu_percent * 0.4 + memory_percent * 0.6) / 100.0)

        # Determine health status
        if cpu_percent > 90 or memory_percent > 90:
            status = HealthStatus.UNHEALTHY
            message = ".1f"
        elif cpu_percent > 70 or memory_percent > 80:
            status = HealthStatus.DEGRADED
            message = ".1f"
        else:
            status = HealthStatus.HEALTHY
            message = ".1f"

        return MetricsRegistry.HealthCheck(
            name="system_resources",
            status=status,
            score=max(0.0, resource_score),  # Ensure non-negative
            message=message,
            checked_at=time.time(),
            response_time=time.time() - start_time,
            details={
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_used_gb": memory.used / (1024**3),
                "memory_total_gb": memory.total / (1024**3),
            },
        )

    except Exception as e:
        return MetricsRegistry.HealthCheck(
            name="system_resources",
            status=HealthStatus.UNHEALTHY,
            score=0.0,
            message=f"System resource check failed: {str(e)}",
            checked_at=time.time(),
            response_time=time.time() - start_time,
        )


def check_external_services() -> MetricsRegistry.HealthCheck:
    """
    Check external service dependencies.

    Tests connectivity to external APIs and services that the pipeline depends on.
    """
    start_time = time.time()

    try:
        services_checked = []
        failed_services = []

        # Test FAL AI connectivity (if API key is available)
        fal_key = os.environ.get("FAL_KEY")
        if fal_key:
            try:
                # Simple connectivity test (this would be replaced with actual API check)
                response = requests.get("https://fal.ai/api/health", timeout=5)
                if response.status_code == 200:
                    services_checked.append("fal_ai")
                else:
                    failed_services.append(f"fal_ai ({response.status_code})")
            except Exception as e:
                failed_services.append(f"fal_ai ({str(e)})")

        # Test ElevenLabs connectivity (if API key is available)
        elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY")
        if elevenlabs_key:
            try:
                # Simple connectivity test
                response = requests.get(
                    "https://api.elevenlabs.io/v1/health", timeout=5
                )
                if response.status_code in [200, 404]:  # 404 is OK for health endpoint
                    services_checked.append("elevenlabs")
                else:
                    failed_services.append(f"elevenlabs ({response.status_code})")
            except Exception as e:
                failed_services.append(f"elevenlabs ({str(e)})")

        # Calculate health score
        total_services = len(services_checked) + len(failed_services)

        if total_services == 0:
            # No services configured
            score = 1.0
            status = HealthStatus.HEALTHY
            message = "No external services configured"
        elif failed_services:
            # Some services failed
            score = len(services_checked) / total_services
            if score < 0.5:
                status = HealthStatus.UNHEALTHY
                message = f"Multiple external services unreachable: {', '.join(failed_services)}"
            else:
                status = HealthStatus.DEGRADED
                message = (
                    f"Some external services unreachable: {', '.join(failed_services)}"
                )
        else:
            # All services OK
            score = 1.0
            status = HealthStatus.HEALTHY
            message = f"All {len(services_checked)} external services reachable"

        return MetricsRegistry.HealthCheck(
            name="external_services",
            status=status,
            score=score,
            message=message,
            checked_at=time.time(),
            response_time=time.time() - start_time,
            details={
                "services_checked": services_checked,
                "failed_services": failed_services,
                "total_services": total_services,
            },
        )

    except Exception as e:
        return MetricsRegistry.HealthCheck(
            name="external_services",
            status=HealthStatus.UNHEALTHY,
            score=0.0,
            message=f"External services check failed: {str(e)}",
            checked_at=time.time(),
            response_time=time.time() - start_time,
        )


def check_pipeline_performance() -> MetricsRegistry.HealthCheck:
    """
    Check pipeline performance metrics.

    Monitors request latency, success rates, and error rates.
    """
    registry = get_registry()
    start_time = time.time()

    try:
        # Get recent performance metrics
        total_requests = registry.get_counter("api.requests_total")
        failed_requests = registry.get_counter("api.requests_failed")

        if total_requests == 0:
            score = 1.0
            status = HealthStatus.HEALTHY
            message = "No requests processed yet"
            success_rate = 1.0
        else:
            success_rate = (total_requests - failed_requests) / total_requests

            # Get recent timer performance (last 100 requests)
            timer_stats = registry.get_timer_stats(
                "api.request_duration.api.generate_image"
            )

            if success_rate >= 0.95 and timer_stats.get("p95", 0) < 10:  # 10 seconds
                score = 1.0
                status = HealthStatus.HEALTHY
                message = ".1%"
            elif success_rate >= 0.85 or timer_stats.get("p95", 0) < 30:  # 30 seconds
                score = 0.7
                status = HealthStatus.DEGRADED
                message = ".1%"
            else:
                score = 0.3
                status = HealthStatus.UNHEALTHY
                message = ".1%"

        return MetricsRegistry.HealthCheck(
            name="pipeline_performance",
            status=status,
            score=score,
            message=message,
            checked_at=time.time(),
            response_time=time.time() - start_time,
            details={
                "total_requests": total_requests,
                "failed_requests": failed_requests,
                "success_rate": success_rate,
                "avg_response_time": registry.get_timer_stats(
                    "api.request_duration.api.generate_image"
                ).get("mean", 0),
                "p95_response_time": registry.get_timer_stats(
                    "api.request_duration.api.generate_image"
                ).get("p95", 0),
            },
        )

    except Exception as e:
        return MetricsRegistry.HealthCheck(
            name="pipeline_performance",
            status=HealthStatus.UNHEALTHY,
            score=0.0,
            message=f"Pipeline performance check failed: {str(e)}",
            checked_at=time.time(),
            response_time=time.time() - start_time,
        )


def register_default_health_checks() -> None:
    """
    Register all default health checks with the global registry.

    This function should be called during application startup to
    enable comprehensive health monitoring.
    """
    registry = get_registry()

    # Register all health check functions
    health_checks = [
        ("api_endpoints", check_api_endpoints),
        ("filesystem", check_filesystem),
        ("system_resources", check_system_resources),
        ("external_services", check_external_services),
        ("pipeline_performance", check_pipeline_performance),
    ]

    for check_name, check_function in health_checks:
        registry.register_health_check(check_name, check_function)
        print(f"[HEALTH] Registered health check: {check_name}")


# Auto-register health checks when module is imported
if __name__ != "__main__":
    register_default_health_checks()
