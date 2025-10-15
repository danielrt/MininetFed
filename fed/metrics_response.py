import json
from enum import Enum
from typing import Any

class MetricType(Enum):
    ACCURACY = "accuracy"

class MetricsResponse:
    def __init__(self, metrics : dict[MetricType, Any]):
        self.metrics = metrics

    @classmethod
    def from_json(cls, json_str ):
        metrics = json.loads(json_str)
        return cls(metrics)