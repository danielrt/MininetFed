import json
from numpy import ndarray
from mininetfed.core.utils import base64_to_ndarray, ndarray_to_base64

class TrainingData:
    def __init__(self, node_id : str, success : bool, round_id : int, weights : list[ndarray]):
        self.client_id = node_id
        self.success = success
        self.round_id = round_id
        self.weights = weights

    @classmethod
    def from_json(cls, json_str : str) -> "TrainingData":
        json_data = json.loads(json_str)
        client_id = json_data["client_id"]
        success = json_data["success"]
        round_id = json_data["round_id"]
        weights = [base64_to_ndarray(p) for p in json_data["weights"]]
        return cls(node_id=client_id, success=success, round_id=round_id, weights=weights)

    @classmethod
    def from_dict(cls, d: dict) -> "TrainingData":
        client_id = d["client_id"]
        success = d["success"]
        round_id = d["round_id"]
        weights = [base64_to_ndarray(p) for p in d["weights"]]
        return cls(node_id=client_id, success=success, round_id=round_id, weights=weights)

    def to_dict(self) -> dict:
        weights_base64 = [ndarray_to_base64(w) for w in self.weights]
        return {"client_id": self.client_id, "success": self.success, "round_id": self.round_id, "weights": weights_base64}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def get_node_id(self) -> str:
        return self.client_id
    def was_success(self) -> bool:
        return self.success

    def get_round_id(self) -> int:
        return self.round_id

    def get_weights(self) -> list[ndarray]:
        return self.weights



