import json
from typing import TypeAlias, Union

JSONSerializableType: TypeAlias = Union[
    None, bool, int, float, str,
    list["JSONSerializableType"],
    dict[str, "JSONSerializableType"],
]

class DatasetInfo:
    def __init__(self, client_id: str, num_samples : int, infos: dict[str, JSONSerializableType]):
        self.client_id = client_id
        self.num_samples = num_samples
        self.info = infos

    def get_client_id(self) -> str:
        return self.client_id

    def set_dataset_info(self, dataset_info_name: str, info: JSONSerializableType):
        self.info[dataset_info_name] = info

    def get_info(self, info: str) -> JSONSerializableType:
        return self.info[info]

    def get_num_samples(self) -> int:
        return self.info["num_samples"]

    def to_json(self) -> str:
        return json.dumps({"client_id": self.client_id, "num_samples": self.num_samples, "info": self.info})

    @classmethod
    def from_json(cls, json_str : str) -> "DatasetInfo":
        json_data = json.loads(json_str)
        client_id = json_data["client_id"]
        num_samples = json_data["num_samples"]
        info = json_data["info"]
        return cls(client_id, num_samples, info)