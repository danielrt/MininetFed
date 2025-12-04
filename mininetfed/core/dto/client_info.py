import json

from mininetfed.core.utils import JSONSerializableType

class ClientInfo:
    def __init__(self, client_id : str):
        self.client_id = client_id
        self.infos = {}

    def get_client_id(self):
        return self.client_id

    def set_info(self, info_name: str, info: JSONSerializableType):
        self.infos[info_name] = info

    def get_info(self, info: str) -> JSONSerializableType:
        return self.infos[info]

    def to_dict(self) -> dict:
        return {"client_id": self.client_id, "infos": self.infos}

    @classmethod
    def from_dict(cls, d : dict) -> "ClientInfo":
        client_id = d["infos"]
        infos = d["infos"]
        c = cls(client_id)
        c.infos = infos
        return c

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str : str) -> "ClientInfo":
        json_data = json.loads(json_str)
        client_id = json_data["client_id"]
        infos = json_data["infos"]
        c = cls(client_id)
        c.infos = infos
        return c