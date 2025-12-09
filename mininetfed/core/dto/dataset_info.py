import json
from mininetfed.core.utils import JSONSerializableType


class DatasetInfo:
    def __init__(self, client_id: str, num_samples: int):
        self.client_id = client_id
        self.num_samples = num_samples
        self.info: dict[str, JSONSerializableType] = {}

    def get_client_id(self) -> str:
        return self.client_id

    def set_dataset_info(self, dataset_info_name: str, info: JSONSerializableType) -> None:
        self.info[dataset_info_name] = info

    def get_info(self, info_name: str) -> JSONSerializableType:
        return self.info[info_name]

    def get_num_samples(self) -> int:
        return self.num_samples

    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "num_samples": self.num_samples,
            "info": self.info,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DatasetInfo":
        client_id = d["client_id"]
        num_samples = d["num_samples"]
        info = d.get("info", {})
        c = cls(client_id, num_samples)
        c.info = info
        return c

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "DatasetInfo":
        d = json.loads(json_str)
        return cls.from_dict(d)
