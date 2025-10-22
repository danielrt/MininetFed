from fed.metrics_response import MetricsResponse
from fed.training_response import TrainingResponse


class ClientState:
    def __init__(self, client_id):
        self.client_id = client_id
        self.metrics = []
        self.selected = []
        self.training_status = []

    def get_client_id(self):
        return self.client_id

    def set_selection_for_round(self, round_id : int,  selected : bool):
        for i in range(len(self.selected), round_id):
            self.selected.append(False)
        self.selected[round_id] = selected

    def was_selected_for_round(self, round_id : int):
        if round_id < len(self.selected):
            return self.selected[round_id]
        else:
            return False

    def get_selection_for_all_rounds(self):
        return self.selected

    def set_training_status_for_round(self, round_id, training_status : bool):
        for i in range(len(self.training_status), round_id):
            self.training_status.append(False)
        self.training_status[round_id] = training_status

    def get_training_status_for_round(self, round_id : int):
        if round_id < len(self.training_status):
            return self.training_status[round_id]
        else:
            return None

    def get_training_status_for_all_rounds(self):
        return self.training_status

    def set_metrics_for_round(self, round_id : int, metrics : MetricsResponse):
        for i in range(len(self.metrics), round_id):
            self.metrics.append(False)
        self.metrics.append(metrics)

    def get_metrics_for_round(self, round_id : int):
        if round_id < len(self.metrics):
            return self.metrics[round_id]
        else:
            return None

    def get_metrics_for_all_rounds(self):
        return self.metrics
