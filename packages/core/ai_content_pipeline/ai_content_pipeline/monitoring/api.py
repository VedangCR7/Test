"""
RESTful monitoring API endpoints for the AI Content Pipeline.

Provides HTTP endpoints for:
- GET /metrics - Real-time metrics and statistics
- GET /health - Comprehensive health status with checks
- GET /alerts - Active and resolved alerts
- POST /alerts/{id}/resolve - Resolve specific alerts

All endpoints return JSON responses and support CORS for web dashboard integration.
"""

import json
import time
from typing import Dict, Any
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import urllib.parse

from .metrics import get_registry, HealthStatus


class MonitoringAPIHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for monitoring API endpoints.

    Supports GET requests for metrics, health, and alerts endpoints.
    Includes proper CORS headers for web dashboard integration.
    """

    def __init__(self, *args, registry=None, **kwargs):
        self.registry = registry or get_registry()
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        """Handle GET requests for monitoring endpoints."""
        try:
            # Parse the request path
            parsed_path = urllib.parse.urlparse(self.path)
            path_parts = parsed_path.path.strip("/").split("/")

            # Route to appropriate handler
            if path_parts == ["metrics"]:
                self._handle_metrics()
            elif path_parts == ["health"]:
                self._handle_health()
            elif path_parts == ["alerts"]:
                self._handle_alerts()
            elif (
                len(path_parts) == 3
                and path_parts[0] == "alerts"
                and path_parts[2] == "resolve"
            ):
                # POST endpoint handled separately
                self._send_error(405, "Method Not Allowed")
            else:
                self._send_error(404, "Endpoint not found")

        except Exception as e:
            self.logger.error(f"Error handling GET request: {e}")
            self._send_error(500, f"Internal server error: {str(e)}")

    def do_POST(self) -> None:
        """Handle POST requests for alert resolution."""
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path_parts = parsed_path.path.strip("/").split("/")

            if (
                len(path_parts) == 3
                and path_parts[0] == "alerts"
                and path_parts[2] == "resolve"
            ):
                alert_id = path_parts[1]
                self._handle_resolve_alert(alert_id)
            else:
                self._send_error(404, "Endpoint not found")

        except Exception as e:
            self.logger.error(f"Error handling POST request: {e}")
            self._send_error(500, f"Internal server error: {str(e)}")

    def do_OPTIONS(self) -> None:
        """Handle OPTIONS requests for CORS preflight."""
        self._send_cors_headers()
        self.end_headers()

    def _handle_metrics(self) -> None:
        """Handle GET /metrics endpoint."""
        try:
            metrics_data = self.registry.get_metrics_snapshot()

            # Add computed metrics
            total_requests = self.registry.get_counter("api.requests_total")
            failed_requests = self.registry.get_counter("api.requests_failed")

            if total_requests > 0:
                success_rate = (total_requests - failed_requests) / total_requests
                metrics_data["computed"] = {
                    "api_success_rate": success_rate,
                    "error_rate_percent": (failed_requests / total_requests) * 100,
                }
            else:
                metrics_data["computed"] = {
                    "api_success_rate": 1.0,
                    "error_rate_percent": 0.0,
                }

            self._send_json_response(200, metrics_data)

        except Exception as e:
            self.logger.error(f"Error generating metrics: {e}")
            self._send_error(500, f"Failed to generate metrics: {str(e)}")

    def _handle_health(self) -> None:
        """Handle GET /health endpoint."""
        try:
            # Run health checks
            health_results = self.registry.run_health_checks()
            overall_score = self.registry.get_overall_health_score()

            # Determine overall status
            if overall_score >= 0.9:
                overall_status = HealthStatus.HEALTHY
            elif overall_score >= 0.7:
                overall_status = HealthStatus.DEGRADED
            else:
                overall_status = HealthStatus.UNHEALTHY

            health_data = {
                "status": overall_status.value,
                "score": overall_score,
                "timestamp": time.time(),
                "checks": {
                    name: {
                        "status": check.status.value,
                        "score": check.score,
                        "message": check.message,
                        "checked_at": check.checked_at,
                        "response_time": check.response_time,
                        "details": check.details,
                    }
                    for name, check in health_results.items()
                },
            }

            # Set HTTP status code based on health
            http_status = 200 if overall_status == HealthStatus.HEALTHY else 503
            self._send_json_response(http_status, health_data)

        except Exception as e:
            self.logger.error(f"Error generating health status: {e}")
            self._send_error(500, f"Failed to generate health status: {str(e)}")

    def _handle_alerts(self) -> None:
        """Handle GET /alerts endpoint."""
        try:
            active_alerts = self.registry.get_active_alerts()
            alert_history = self.registry.get_alert_history(limit=50)

            alerts_data = {
                "active_count": len(active_alerts),
                "total_history": len(alert_history),
                "timestamp": time.time(),
                "active_alerts": [
                    {
                        "id": f"{alert.rule_name}_{alert.triggered_at}",
                        "rule_name": alert.rule_name,
                        "severity": alert.severity.value,
                        "message": alert.message,
                        "value": alert.value,
                        "threshold": alert.threshold,
                        "triggered_at": alert.triggered_at,
                        "tags": alert.tags,
                    }
                    for alert in active_alerts
                ],
                "recent_history": [
                    {
                        "rule_name": alert.rule_name,
                        "severity": alert.severity.value,
                        "message": alert.message,
                        "value": alert.value,
                        "threshold": alert.threshold,
                        "triggered_at": alert.triggered_at,
                        "resolved_at": alert.resolved_at,
                        "tags": alert.tags,
                    }
                    for alert in alert_history[-20:]  # Last 20 alerts
                ],
            }

            self._send_json_response(200, alerts_data)

        except Exception as e:
            self.logger.error(f"Error generating alerts data: {e}")
            self._send_error(500, f"Failed to generate alerts data: {str(e)}")

    def _handle_resolve_alert(self, alert_id: str) -> None:
        """Handle POST /alerts/{id}/resolve endpoint."""
        try:
            if self.registry.resolve_alert(alert_id):
                self._send_json_response(
                    200,
                    {
                        "status": "success",
                        "message": f"Alert {alert_id} resolved",
                        "timestamp": time.time(),
                    },
                )
            else:
                self._send_json_response(
                    404,
                    {
                        "status": "error",
                        "message": f"Alert {alert_id} not found or already resolved",
                        "timestamp": time.time(),
                    },
                )

        except Exception as e:
            self.logger.error(f"Error resolving alert {alert_id}: {e}")
            self._send_error(500, f"Failed to resolve alert: {str(e)}")

    def _send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        """Send a JSON response with appropriate headers."""
        self._send_cors_headers()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

        json_response = json.dumps(data, indent=2, default=str)
        self.wfile.write(json_response.encode("utf-8"))

    def _send_error(self, status_code: int, message: str) -> None:
        """Send an error response."""
        self._send_cors_headers()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        error_data = {
            "error": message,
            "status_code": status_code,
            "timestamp": time.time(),
        }
        json_response = json.dumps(error_data, indent=2)
        self.wfile.write(json_response.encode("utf-8"))

    def _send_cors_headers(self) -> None:
        """Send CORS headers for web dashboard integration."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    @property
    def logger(self):
        """Get logger instance."""
        import logging

        return logging.getLogger(__name__)

    def log_message(self, format, *args):
        """Override to use our logger."""
        self.logger.info(format % args)


class MonitoringAPIServer:
    """
    HTTP server for monitoring API endpoints.

    Runs in a separate thread to avoid blocking the main application.
    Provides graceful shutdown and health monitoring.
    """

    def __init__(self, host: str = "localhost", port: int = 8080, registry=None):
        """
        Initialize the monitoring API server.

        Args:
            host: Server host (default: localhost)
            port: Server port (default: 8080)
            registry: Metrics registry instance (default: global registry)
        """
        self.host = host
        self.port = port
        self.registry = registry or get_registry()
        self.server = None
        self.thread = None
        self.running = False

        # Create custom handler class with registry
        class HandlerWithRegistry(MonitoringAPIHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(
                    *args, registry=self.server_instance.registry, **kwargs
                )

        self.handler_class = HandlerWithRegistry

    def start(self) -> None:
        """Start the monitoring API server in a background thread."""
        if self.running:
            return

        def run_server():
            try:
                self.server = HTTPServer((self.host, self.port), self.handler_class)
                self.server.timeout = 1  # Allow for shutdown checks
                self.running = True

                print(
                    f"[MONITORING] API server started on http://{self.host}:{self.port}"
                )
                print("[MONITORING] Endpoints available:")
                print("[MONITORING]   GET  /metrics - Real-time metrics")
                print("[MONITORING]   GET  /health  - Health status")
                print("[MONITORING]   GET  /alerts  - Active alerts")
                print("[MONITORING]   POST /alerts/{id}/resolve - Resolve alerts")

                while self.running:
                    try:
                        self.server.serve_forever()
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print(f"[MONITORING] Server error: {e}")
                        time.sleep(1)

            except Exception as e:
                print(f"[MONITORING] Failed to start server: {e}")
            finally:
                self.running = False

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()

        # Wait a bit for server to start
        time.sleep(0.5)

    def stop(self) -> None:
        """Stop the monitoring API server."""
        if not self.running:
            return

        self.running = False

        if self.server:
            self.server.shutdown()
            self.server.server_close()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        print("[MONITORING] API server stopped")

    def is_running(self) -> bool:
        """Check if the server is running."""
        return self.running and self.thread and self.thread.is_alive()

    def get_status(self) -> Dict[str, Any]:
        """Get server status information."""
        return {
            "running": self.is_running(),
            "host": self.host,
            "port": self.port,
            "endpoints": [
                f"http://{self.host}:{self.port}/metrics",
                f"http://{self.host}:{self.port}/health",
                f"http://{self.host}:{self.port}/alerts",
            ],
        }


# Convenience functions for easy integration
def start_monitoring_server(
    host: str = "localhost", port: int = 8080
) -> MonitoringAPIServer:
    """
    Start the monitoring API server.

    Args:
        host: Server host
        port: Server port

    Returns:
        MonitoringAPIServer instance
    """
    server = MonitoringAPIServer(host, port)
    server.start()
    return server


def get_metrics_endpoint() -> str:
    """Get the metrics endpoint URL."""
    return "http://localhost:8080/metrics"


def get_health_endpoint() -> str:
    """Get the health endpoint URL."""
    return "http://localhost:8080/health"


def get_alerts_endpoint() -> str:
    """Get the alerts endpoint URL."""
    return "http://localhost:8080/alerts"


# Global server instance
_monitoring_server = None


def initialize_monitoring_api(host: str = "localhost", port: int = 8080) -> None:
    """Initialize the monitoring API server globally."""
    global _monitoring_server
    if _monitoring_server is None:
        _monitoring_server = start_monitoring_server(host, port)


def shutdown_monitoring_api() -> None:
    """Shutdown the global monitoring API server."""
    global _monitoring_server
    if _monitoring_server:
        _monitoring_server.stop()
        _monitoring_server = None
