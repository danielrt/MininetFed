from mininetfed.core.dto.client_info import ClientInfo
from mininetfed.core.dto.metrics import Metrics
from mininetfed.core.dto.dataset_info import DatasetInfo


class ClientState:
    def __init__(self, client_id):
        self.client_id = client_id
        self.dataset_info : DatasetInfo | None = None
        self.client_info : ClientInfo | None = None
        self.metrics : list[Metrics | None] = []
        self.selected : list[bool] = []
        self.training_status : list[bool] = []

    def get_client_id(self) -> str:
        return self.client_id

    def set_dataset_info(self, dataset_info : DatasetInfo):
        self.dataset_info = dataset_info

    def get_dataset_info(self) -> DatasetInfo:
        return self.dataset_info

    def set_client_info(self, client_info : ClientInfo):
        self.client_info = client_info

    def get_client_info(self) -> ClientInfo:
        return self.client_info

    def set_selection_for_round(self, round_id : int,  selected : bool):
        for i in range(len(self.selected), round_id+1):
            self.selected.append(False)
        self.selected[round_id] = selected

    def was_selected_for_round(self, round_id : int) -> bool:
        if round_id < len(self.selected):
            return self.selected[round_id]
        else:
            return False

    def get_selection_for_all_rounds(self):
        return self.selected

    def set_training_status_for_round(self, round_id, training_status : bool):
        for i in range(len(self.training_status), round_id+1):
            self.training_status.append(False)
        self.training_status[round_id] = training_status

    def get_training_status_for_round(self, round_id : int):
        if round_id < len(self.training_status):
            return self.training_status[round_id]
        else:
            return None

    def get_training_status_for_all_rounds(self) -> list[bool]:
        return self.training_status

    def set_metrics_for_round(self, round_id : int, metrics : Metrics):
        for i in range(len(self.metrics), round_id):
            self.metrics.append(None)
        self.metrics.append(metrics)

    def get_metrics_for_round(self, round_id : int) -> Metrics | None:
        if round_id < len(self.metrics):
            return self.metrics[round_id]
        else:
            return None

    def get_metrics_for_all_rounds(self) -> list[Metrics]:
        return self.metrics

