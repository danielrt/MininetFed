import json
from typing import Any

from numpy import ndarray

class ClientTrainingData:
    def __init__(self, client_id : str, success : bool, round_id : int, weights : list[ndarray], num_samples : int, training_args : dict[str, Any]):
        self.client_id = client_id
        self.success = success
        self.round_id = round_id
        self.weights = weights
        self.num_samples = num_samples
        self.training_args = training_args

    @classmethod
    def from_json(cls, json_str : str):
        json_data = json.loads(json_str)
        client_id = json_data["client_id"]
        success = json_data["success"]
        round_id = json_data["round_id"]
        weights = json_data["weights"]
        num_samples = json_data["num_samples"]
        training_args = json_data["training_args"]
        return cls(client_id=client_id, success=success, round_id=round_id, weights=weights, num_samples=num_samples, **training_args)

    def to_json(self):
        return json.dumps({"client_id": self.client_id, "success": self.success, "round_id": self.round_id, "weights": self.weights, "num_samples": self.num_samples, self.training_args : self.training_args })

    def get_client_id(self):
        return self.client_id

    def was_success(self):
        return self.success

    def get_round_id(self):
        return self.round_id

    def get_weights(self):
        return self.weights

    def get_num_samples(self):
        return self.num_samples

    def get_training_args(self):
        return self.training_args

