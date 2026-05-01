"""File: services/llm_config.py
Purpose: Task-specific LLM configurations (temperature, top_p, etc.).
         Allows different behaviors for creative vs. analytical tasks.
"""

from dataclasses import dataclass
from enum import Enum
import os

class TaskType(str, Enum):
    ANALYTICAL = "analytical"    # chapter extraction, schema parsing, refinement
    CREATIVE = "creative"        # viral hooks, titles, repurpose
    SCORING = "scoring"          # clip scoring — balanced
    DEFAULT = "default"

@dataclass
class LLMConfig:
    temperature: float
    top_p: float
    max_tokens: int

# Default configurations
TASK_CONFIGS: dict[TaskType, LLMConfig] = {
    TaskType.ANALYTICAL: LLMConfig(
        temperature=float(os.getenv("LLM_TEMP_ANALYTICAL", "0.1")), 
        top_p=0.9,  
        max_tokens=2048
    ),
    TaskType.CREATIVE: LLMConfig(
        temperature=float(os.getenv("LLM_TEMP_CREATIVE", "0.85")), 
        top_p=0.95, 
        max_tokens=1024
    ),
    TaskType.SCORING: LLMConfig(
        temperature=float(os.getenv("LLM_TEMP_SCORING", "0.4")), 
        top_p=0.9,  
        max_tokens=1024
    ),
    TaskType.DEFAULT: LLMConfig(
        temperature=0.7, 
        top_p=1.0, 
        max_tokens=1024
    ),
}

def get_llm_config(task: TaskType) -> LLMConfig:
    """Retrieve the configuration for a specific task type."""
    return TASK_CONFIGS.get(task, TASK_CONFIGS[TaskType.DEFAULT])
