import base64
import json

import numpy as np
from numpy import ndarray

from fed.dataset_info import DatasetInfo

def ndarray_to_base64(arr: np.ndarray) -> dict:
    """Convert one ndarray to a base64 JSON-safe dict."""
    return {
        "dtype": str(arr.dtype),
        "shape": arr.shape,
        "data_b64": base64.b64encode(arr.tobytes()).decode("ascii"),
    }

def base64_to_ndarray(entry: dict) -> np.ndarray:
    """Decode one base64 JSON-encoded ndarray."""
    data = base64.b64decode(entry["data_b64"])
    arr = np.frombuffer(data, dtype=np.dtype(entry["dtype"]))
    return arr.reshape(entry["shape"])

class ClientTrainingData:
    def __init__(self, client_id : str, success : bool, round_id : int, weights : list[ndarray]):
        self.client_id = client_id
        self.success = success
        self.round_id = round_id
        self.weights = weights

    @classmethod
    def from_json(cls, json_str : str) -> "ClientTrainingData":
        json_data = json.loads(json_str)
        client_id = json_data["client_id"]
        success = json_data["success"]
        round_id = json_data["round_id"]
        weights = [base64_to_ndarray(p) for p in json_data["weights"]]
        return cls(client_id=client_id, success=success, round_id=round_id, weights=weights)

    def to_json(self) -> str:
        weights_base64 = [ndarray_to_base64(w) for w in self.weights]
        return json.dumps({"client_id": self.client_id, "success": self.success, "round_id": self.round_id, "weights": weights_base64 })

    def get_client_id(self) -> str:
        return self.client_id

    def was_success(self) -> bool:
        return self.success

    def get_round_id(self) -> int:
        return self.round_id

    def get_weights(self) -> list[ndarray]:
        return self.weights



