import json
from enum import Enum
from typing import Any

class MetricType(Enum):
    ACCURACY = "accuracy"

class MetricsResponse:
    def __init__(self, client_id : str, metrics : dict[str, Any]):
        self.client_id = client_id
        self.metrics = metrics

    @classmethod
    def from_json(cls, json_str : str) -> "MetricsResponse":
        json_data = json.loads(json_str)
        client_id = json_data["client_id"]
        metrics = json_data["metrics"]
        return cls(client_id=client_id, metrics=metrics)

    def to_json(self) -> str:
        return json.dumps({"client_id": self.client_id, "metrics": self.metrics})

    def get_client_id(self) -> str:
        return self.client_id

    def get_metrics(self) -> dict[str, Any]:
        return self.metrics