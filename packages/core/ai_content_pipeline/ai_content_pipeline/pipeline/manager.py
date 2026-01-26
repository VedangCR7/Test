"""
Main pipeline manager for AI Content Pipeline

Orchestrates the execution of content creation chains with multiple AI models.
"""

import os
import time
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from .chain import ContentCreationChain, ChainResult, PipelineStep, StepType
from .executor import ChainExecutor
from ..models.text_to_image import UnifiedTextToImageGenerator
from ..models.image_understanding import UnifiedImageUnderstandingGenerator
from ..models.prompt_generation import UnifiedPromptGenerator
from ..models.image_to_image import UnifiedImageToImageGenerator
from ..utils.file_manager import FileManager
from ..config.constants import SUPPORTED_MODELS, DEFAULT_CHAIN_CONFIG
from ..monitoring.metrics import (
    get_registry, record_request, record_error, record_data_processed,
    increment_counter, set_gauge, record_timer, record_histogram
)
from ..monitoring.metrics_config import initialize_alert_rules
from ..monitoring.health_checks import register_default_health_checks
from ..monitoring.api import initialize_monitoring_api, shutdown_monitoring_api
import functools
import logging

logger = logging.getLogger(__name__)


def monitor_operation(operation_name: str):
    """
    Decorator to monitor pipeline operations with automatic metrics collection.

    Tracks execution time, success/failure rates, and errors.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            start_time = time.time()
            success = False

            try:
                # Record operation start
                increment_counter(f"pipeline.operations_total", tags={"operation": operation_name})
                set_gauge(f"pipeline.active_operations.{operation_name}", 1, tags={"operation": operation_name})

                result = func(self, *args, **kwargs)
                success = True

                # Record success metrics
                increment_counter(f"pipeline.operations_success", tags={"operation": operation_name})

                return result

            except Exception as e:
                # Record error metrics
                record_error(f"pipeline_operation_error", str(e), tags={"operation": operation_name})
                increment_counter(f"pipeline.operations_failed", tags={"operation": operation_name})
                raise

            finally:
                # Record timing and cleanup
                execution_time = time.time() - start_time
                record_timer(f"pipeline.operation_duration.{operation_name}", execution_time)
                record_histogram(f"pipeline.operation_duration_histogram.{operation_name}", execution_time)

                set_gauge(f"pipeline.active_operations.{operation_name}", 0, tags={"operation": operation_name})

                logger.info(f"Operation '{operation_name}' completed in {execution_time:.2f}s (success: {success})")

        return wrapper
    return decorator


class AIPipelineManager:
    """
    Main manager for AI content creation pipelines.
    
    Handles chain creation, execution, cost estimation, and result management.
    """
    
    def __init__(self, base_dir: str = None, enable_monitoring: bool = True):
        """
        Initialize the pipeline manager.

        Args:
            base_dir: Base directory for pipeline operations
            enable_monitoring: Whether to enable comprehensive monitoring
        """
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.output_dir = self.base_dir / "output"
        self.temp_dir = self.output_dir / "temp"
        self.enable_monitoring = enable_monitoring

        # Initialize components
        self.file_manager = FileManager(self.base_dir)
        self.executor = ChainExecutor(self.file_manager)

        # Initialize monitoring system if enabled
        if self.enable_monitoring:
            self._initialize_monitoring()

        # Record manager initialization
        if self.enable_monitoring:
            increment_counter("pipeline.manager_initializations")
            set_gauge("pipeline.manager_active", 1)
            logger.info("AI Pipeline Manager initialized with monitoring enabled")

    def _initialize_monitoring(self) -> None:
        """Initialize comprehensive monitoring system."""
        try:
            # Initialize alert rules
            initialize_alert_rules()

            # Register health checks
            register_default_health_checks()

            # Start monitoring API server if configured
            monitoring_host = os.environ.get("MONITORING_HOST", "localhost")
            monitoring_port = int(os.environ.get("MONITORING_PORT", "8080"))

            if os.environ.get("ENABLE_MONITORING_API", "true").lower() == "true":
                initialize_monitoring_api(monitoring_host, monitoring_port)
                logger.info(f"Monitoring API server started on http://{monitoring_host}:{monitoring_port}")

            # Record successful initialization
            increment_counter("monitoring.system_initializations")

        except Exception as e:
            logger.error(f"Failed to initialize monitoring system: {e}")
            # Don't fail manager initialization if monitoring fails
            record_error("monitoring_initialization_error", str(e))

    def get_monitoring_status(self) -> Dict[str, Any]:
        """
        Get comprehensive monitoring system status.

        Returns:
            Dict with monitoring system health and metrics
        """
        if not self.enable_monitoring:
            return {"enabled": False, "message": "Monitoring system disabled"}

        try:
            registry = get_registry()
            health_checks = registry.run_health_checks()
            overall_score = registry.get_overall_health_score()

            return {
                "enabled": True,
                "overall_health_score": overall_score,
                "health_checks": {
                    name: {
                        "status": check.status.value,
                        "score": check.score,
                        "message": check.message
                    }
                    for name, check in health_checks.items()
                },
                "active_alerts": len(registry.get_active_alerts()),
                "total_metrics_collections": registry.get_metrics_snapshot().get("total_collections", 0),
                "uptime_seconds": registry.get_metrics_snapshot().get("uptime_seconds", 0)
            }
        except Exception as e:
            logger.error(f"Failed to get monitoring status: {e}")
            return {"enabled": True, "error": str(e)}

    def shutdown_monitoring(self) -> None:
        """Shutdown monitoring system gracefully."""
        if self.enable_monitoring:
            try:
                shutdown_monitoring_api()
                set_gauge("pipeline.manager_active", 0)
                logger.info("Monitoring system shutdown completed")
            except Exception as e:
                logger.error(f"Error during monitoring shutdown: {e}")

        # Initialize model generators
        self.text_to_image = UnifiedTextToImageGenerator()
        self.image_understanding = UnifiedImageUnderstandingGenerator()
        self.prompt_generation = UnifiedPromptGenerator()
        self.image_to_image = UnifiedImageToImageGenerator()

        # Initialize monitoring
        initialize_alert_rules()
        self.metrics_registry = get_registry()

        # Record initialization
        increment_counter("pipeline.initializations")
        set_gauge("pipeline.status", 1)  # 1 = healthy
        
        # Create directories
        self.output_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        
        print(f"✅ AI Pipeline Manager initialized (base: {self.base_dir})")
    
    @monitor_operation("create_chain_from_config")
    def create_chain_from_config(self, config_path: str) -> ContentCreationChain:
        """
        Create a content creation chain from configuration file.
        
        Args:
            config_path: Path to YAML or JSON configuration file
            
        Returns:
            ContentCreationChain instance
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        # Load configuration
        with open(config_file, 'r') as f:
            if config_file.suffix.lower() in ['.yaml', '.yml']:
                config = yaml.safe_load(f)
            elif config_file.suffix.lower() == '.json':
                config = json.load(f)
            else:
                raise ValueError(f"Unsupported configuration format: {config_file.suffix}")
        
        return ContentCreationChain.from_config(config)
    
    def create_simple_chain(
        self,
        steps: List[str],
        models: Dict[str, str] = None,
        name: str = "simple_chain"
    ) -> ContentCreationChain:
        """
        Create a simple chain with basic configuration.
        
        Args:
            steps: List of step types (e.g., ["text_to_image", "image_to_video"])
            models: Optional model selection for each step
            name: Name for the chain
            
        Returns:
            ContentCreationChain instance
        """
        models = models or {}
        pipeline_steps = []
        
        for step_type in steps:
            if step_type not in [s.value for s in StepType]:
                raise ValueError(f"Unsupported step type: {step_type}")
            
            # Get default model for step type
            available_models = SUPPORTED_MODELS.get(step_type, [])
            if not available_models:
                raise ValueError(f"No models available for step type: {step_type}")
            
            model = models.get(step_type, available_models[0])
            
            pipeline_steps.append(PipelineStep(
                step_type=StepType(step_type),
                model=model,
                params={}
            ))
        
        return ContentCreationChain(name, pipeline_steps)
    
    @monitor_operation("execute_chain")
    def execute_chain(
        self,
        chain: ContentCreationChain,
        input_data: str,
        **kwargs
    ) -> ChainResult:
        """
        Execute a content creation chain.

        Args:
            chain: ContentCreationChain to execute
            input_data: Initial input data (text, image path, or video path)
            **kwargs: Additional execution parameters

        Returns:
            ChainResult with execution results
        """
        start_time = time.time()
        chain_name = chain.name or "unnamed_chain"

        # Record chain execution attempt
        increment_counter("pipeline.chains_executed_total", tags={"chain": chain_name})

        # Validate chain
        errors = chain.validate()
        if errors:
            record_error("validation_error", f"Chain validation failed: {'; '.join(errors)}",
                        tags={"chain": chain_name})
            return ChainResult(
                success=False,
                steps_completed=0,
                total_steps=len(chain.steps),
                total_cost=0.0,
                total_time=0.0,
                outputs={},
                error=f"Chain validation failed: {'; '.join(errors)}"
            )

        print(f"[EXECUTE] Executing chain: {chain.name}")
        print(f"[INPUT] Input ({chain.get_initial_input_type()}): {input_data[:100]}{'...' if len(input_data) > 100 else ''}")

        # Execute chain
        try:
            result = self.executor.execute(chain, input_data, **kwargs)

            # Record execution metrics
            execution_time = time.time() - start_time
            record_timer("pipeline.chain_execution_duration", execution_time,
                        tags={"chain": chain_name, "success": str(result.success)})

            if result.success:
                increment_counter("pipeline.chains_completed", tags={"chain": chain_name})
                record_data_processed("pipeline", result.steps_completed, execution_time,
                                    tags={"chain": chain_name})

                # Update success rate gauge
                total_chains = self.metrics_registry.get_counter("pipeline.chains_executed_total")
                completed_chains = self.metrics_registry.get_counter("pipeline.chains_completed")
                if total_chains > 0:
                    success_rate = completed_chains / total_chains
                    set_gauge("pipeline.success_rate", success_rate)

            else:
                record_error("execution_error", result.error or "Unknown execution error",
                           tags={"chain": chain_name})

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Execution failed: {str(e)}"

            record_error("execution_exception", error_msg, tags={"chain": chain_name})
            record_timer("pipeline.chain_execution_duration", execution_time,
                        tags={"chain": chain_name, "success": "false"})

            return ChainResult(
                success=False,
                steps_completed=0,
                total_steps=len(chain.steps),
                total_cost=0.0,
                total_time=execution_time,
                outputs={},
                error=error_msg
            )
    
    @monitor_operation("quick_create_video")
    def quick_create_video(
        self,
        text: str,
        image_model: str = "auto",
        video_model: str = "auto",
        output_dir: str = None
    ) -> ChainResult:
        """
        Quick method to create video from text using recommended models.
        
        Args:
            text: Text prompt for content creation
            image_model: Model for text-to-image ("auto" for smart selection)
            video_model: Model for image-to-video ("auto" for smart selection)
            output_dir: Custom output directory
            
        Returns:
            ChainResult with creation results
        """
        # Create simple text-to-video chain
        chain = self.create_simple_chain(
            steps=["text_to_image", "image_to_video"],
            models={
                "text_to_image": image_model,
                "image_to_video": video_model
            },
            name="quick_video_creation"
        )
        
        # Execute with custom output directory
        kwargs = {}
        if output_dir:
            kwargs["output_dir"] = output_dir
        
        return self.execute_chain(chain, text, **kwargs)
    
    def estimate_chain_cost(self, chain: ContentCreationChain) -> Dict[str, Any]:
        """
        Get detailed cost estimation for a chain.
        
        Args:
            chain: ContentCreationChain to estimate
            
        Returns:
            Dictionary with cost breakdown
        """
        total_cost = 0.0
        step_costs = []
        
        for step in chain.get_enabled_steps():
            cost = self._estimate_step_cost(step)
            total_cost += cost
            
            step_costs.append({
                "step": step.step_type.value,
                "model": step.model,
                "cost": cost
            })
        
        return {
            "total_cost": total_cost,
            "step_costs": step_costs,
            "currency": "USD"
        }
    
    def _estimate_step_cost(self, step: PipelineStep) -> float:
        """Estimate cost for a single step."""
        if step.step_type == StepType.TEXT_TO_IMAGE:
            return self.text_to_image.estimate_cost(step.model)
        # TODO: Add other step types when implemented
        return 0.0
    
    def get_available_models(self) -> Dict[str, List[str]]:
        """Get all available models by step type."""
        available = {}
        
        # Text-to-image models
        available["text_to_image"] = self.text_to_image.get_available_models()
        
        # Image understanding models
        available["image_understanding"] = self.image_understanding.get_available_models()
        
        # Prompt generation models
        available["prompt_generation"] = self.prompt_generation.get_available_models()
        
        # Image-to-image models
        available["image_to_image"] = self.image_to_image.get_available_models()
        
        # TODO: Add other model types when implemented
        available["image_to_video"] = SUPPORTED_MODELS.get("image_to_video", [])
        available["add_audio"] = SUPPORTED_MODELS.get("add_audio", [])
        available["upscale_video"] = SUPPORTED_MODELS.get("upscale_video", [])
        
        return available
    
    def create_example_configs(self, output_dir: str = None):
        """
        Create example configuration files.
        
        Args:
            output_dir: Directory to create example configs
        """
        output_path = Path(output_dir) if output_dir else self.base_dir / "examples"
        output_path.mkdir(exist_ok=True)
        
        # Simple text-to-image chain
        simple_config = {
            "name": "simple_text_to_image",
            "steps": [
                {
                    "type": "text_to_image",
                    "model": "flux_dev",
                    "params": {
                        "aspect_ratio": "16:9",
                        "style": "cinematic"
                    }
                }
            ],
            "output_dir": "output",
            "cleanup_temp": True
        }
        
        # Full content creation chain
        full_config = {
            "name": "full_content_creation",
            "steps": [
                {
                    "type": "text_to_image",
                    "model": "flux_dev",
                    "params": {
                        "aspect_ratio": "16:9",
                        "style": "cinematic"
                    }
                },
                {
                    "type": "image_to_video",
                    "model": "veo3",
                    "params": {
                        "duration": 8,
                        "motion_level": "medium"
                    }
                },
                {
                    "type": "add_audio",
                    "model": "thinksound",
                    "params": {
                        "prompt": "epic cinematic soundtrack"
                    }
                }
            ],
            "output_dir": "output",
            "temp_dir": "temp",
            "cleanup_temp": True,
            "save_intermediates": False
        }
        
        # Save example configs
        with open(output_path / "simple_chain.yaml", 'w') as f:
            yaml.dump(simple_config, f, default_flow_style=False, indent=2)
        
        with open(output_path / "full_chain.yaml", 'w') as f:
            yaml.dump(full_config, f, default_flow_style=False, indent=2)
        
        print(f"📄 Example configurations created in: {output_path}")
    
    def cleanup_temp_files(self):
        """Clean up temporary files."""
        self.file_manager.cleanup_temp_files()
    
    def __repr__(self) -> str:
        """String representation of the manager."""
        available_models = self.get_available_models()
        total_models = sum(len(models) for models in available_models.values())
        return f"AIPipelineManager(base_dir='{self.base_dir}', models={total_models})"