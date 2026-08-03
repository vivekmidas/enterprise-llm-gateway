from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Basis = Literal["FACT", "INFERENCE", "UNKNOWN"]

@dataclass
class ConfidenceAssessment:
    confidence: float
    basis: Basis

def normalise_confidence(value) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, value))

def review_required(confidence: float, threshold: float) -> bool:
    return normalise_confidence(confidence) < threshold
