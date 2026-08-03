"""
===============================================================================
BLOCK COMMENT: EKP V3 EXTENSIBLE CLEANER BASE & PIPELINE FRAMEWORK
Module: backend/app/knowledge/ekp_v3/cleaner_base.py
Author: EKP Architecture Team
Description:
    Provides abstract base classes, step registry, and dynamic 1..N step execution
    pipeline for document text cleaning. Supports enabling/disabling steps, custom
    step registration, dynamic step configuration, and step-by-step structlog telemetry.
===============================================================================
"""

from __future__ import annotations
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
import structlog

logger = structlog.get_logger(__name__)


class CleanerStep(ABC):
    """
    Abstract base class for a single document cleaning step.
    Supports enabling/disabling, dynamic config parameters, and telemetry.
    """

    def __init__(self, name: str, enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.enabled = enabled
        self.config = config or {}

    @abstractmethod
    def process(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Processes text and returns cleaned text.
        Subclasses must implement this method.
        """
        pass

    def execute(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Executes step if enabled, logging telemetry and execution timing.
        """
        if not self.enabled:
            logger.debug(f"CleanerStep '{self.name}' skipped (disabled)")
            return text

        start_len = len(text)
        start_time = time.perf_counter()

        try:
            cleaned_text = self.process(text, context)
        except Exception as e:
            logger.error(f"CleanerStep '{self.name}' failed with error: {e}", exc_info=True)
            raise e

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        end_len = len(cleaned_text)
        char_delta = end_len - start_len

        logger.info(
            f"CleanerStep '{self.name}' completed",
            step=self.name,
            input_length=start_len,
            output_length=end_len,
            delta_chars=char_delta,
            elapsed_ms=round(elapsed_ms, 3)
        )
        return cleaned_text


class CleanerStepRegistry:
    """Registry for pluggable CleanerStep implementations."""

    _registry: Dict[str, Type[CleanerStep]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a CleanerStep class by name."""
        def decorator(subclass: Type[CleanerStep]):
            cls._registry[name] = subclass
            return subclass
        return decorator

    @classmethod
    def get(cls, name: str) -> Optional[Type[CleanerStep]]:
        return cls._registry.get(name)

    @classmethod
    def list_registered(cls) -> List[str]:
        return list(cls._registry.keys())


class CleanerPipeline:
    """
    Orchestrates sequential execution of 1..N CleanerStep instances.
    Enables dynamic step addition, removal, enabling/disabling, and JSON configuration.
    """

    def __init__(self, steps: Optional[List[CleanerStep]] = None):
        self.steps: List[CleanerStep] = steps or []

    def add_step(self, step: CleanerStep, index: Optional[int] = None) -> CleanerPipeline:
        """Adds a CleanerStep instance to the pipeline at an optional index."""
        if index is not None and 0 <= index <= len(self.steps):
            self.steps.insert(index, step)
        else:
            self.steps.append(step)
        logger.info(f"Added step '{step.name}' to pipeline (total steps: {len(self.steps)})")
        return self

    def remove_step(self, name: str) -> CleanerPipeline:
        """Removes all steps matching the given name."""
        initial_count = len(self.steps)
        self.steps = [s for s in self.steps if s.name != name]
        removed = initial_count - len(self.steps)
        logger.info(f"Removed {removed} step(s) named '{name}' from pipeline")
        return self

    def enable_step(self, name: str) -> CleanerPipeline:
        """Enables steps matching name."""
        for s in self.steps:
            if s.name == name:
                s.enabled = True
                logger.info(f"Enabled step '{name}'")
        return self

    def disable_step(self, name: str) -> CleanerPipeline:
        """Disables steps matching name."""
        for s in self.steps:
            if s.name == name:
                s.enabled = False
                logger.info(f"Disabled step '{name}'")
        return self

    def configure_step(self, name: str, config: Dict[str, Any]) -> CleanerPipeline:
        """Updates configuration dictionary for steps matching name."""
        for s in self.steps:
            if s.name == name:
                s.config.update(config)
                logger.info(f"Configured step '{name}' with {config}")
        return self

    def run(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Executes enabled steps sequentially over input text."""
        if not text:
            return ""

        start_time = time.perf_counter()
        current_text = text

        logger.info(
            "CleanerPipeline execution started",
            total_registered_steps=len(self.steps),
            enabled_steps=sum(1 for s in self.steps if s.enabled),
            initial_text_length=len(text)
        )

        for idx, step in enumerate(self.steps, start=1):
            if step.enabled:
                logger.debug(f"Pipeline running step {idx}/{len(self.steps)}: '{step.name}'")
                current_text = step.execute(current_text, context)

        total_elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "CleanerPipeline execution finished",
            initial_text_length=len(text),
            final_text_length=len(current_text),
            total_elapsed_ms=round(total_elapsed_ms, 3)
        )
        return current_text

    @classmethod
    def from_config(cls, config_list: List[Dict[str, Any]]) -> CleanerPipeline:
        """
        Creates a pipeline from a list of dict configs, e.g.:
        [
            {"step": "whitespace_normalization", "enabled": True, "config": {"max_newlines": 2}},
            {"step": "hyphenation_repair", "enabled": True}
        ]
        """
        pipeline = cls()
        for item in config_list:
            step_name = item.get("step")
            if not step_name:
                continue
            step_class = CleanerStepRegistry.get(step_name)
            if not step_class:
                logger.warning(f"Step '{step_name}' not found in registry. Skipping.")
                continue

            enabled = item.get("enabled", True)
            config = item.get("config", {})
            instance = step_class(name=step_name, enabled=enabled, config=config)
            pipeline.add_step(instance)

        return pipeline
