import json
from typing import Any

from numpy import ndarray

class TrainingResponse:
    def __init__(self, success : bool, weights : list[ndarray], num_samples : int, training_args : dict[str, Any]):
        self.success = success
        self.weights = weights
        self.num_samples = num_samples
        self.training_args = training_args

    @classmethod
    def from_json(cls, json_str : str):
        json_data = json.loads(json_str)
        success = json_data["success"]
        weights = json_data["weights"]
        num_samples = json_data["num_samples"]
        training_args = json_data["training_args"]
        return cls(success=success, weights=weights, num_samples=num_samples, **training_args)

    def to_json(self):
        return json.dumps({ "success": self.success, "weights": self.weights, "num_samples": self.num_samples, self.training_args : self.training_args })

    def get_success(self):
        return self.success

    def get_weights(self):
        return self.weights

    def get_num_samples(self):
        return self.num_samples

    def get_training_args(self):
        return self.training_args

