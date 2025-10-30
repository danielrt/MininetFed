import json
from enum import Enum
from typing import Any, TypeAlias, Union

from fed.utils import JSONSerializableType


class MetricType:
    ACCURACY = "accuracy"

class Metrics:
    def __init__(self, client_id : str, metrics : dict[str, JSONSerializableType]):
        self.client_id = client_id
        self.metrics = metrics

    @classmethod
    def from_json(cls, json_str : str) -> "Metrics":
        json_data = json.loads(json_str)
        client_id = json_data["client_id"]
        metrics = json_data["metrics"]
        return cls(client_id=client_id, metrics=metrics)

    def to_json(self) -> str:
        return json.dumps({"client_id": self.client_id, "metrics": self.metrics})

    def get_client_id(self) -> str:
        return self.client_id

    def get_all_metrics(self) -> dict[str, JSONSerializableType]:
        return self.metrics

    def get_metric(self, metric_name : str) -> JSONSerializableType:
        return self.metrics[metric_name]