from fed.metrics_response import MetricsResponse
from fed.training_response import TrainingResponse


class ClientState:
    def __init__(self, client_id ):
        self.client_id = client_id
        self.metrics = []
        self.training_response = None
        self.selected = False
        self.failed_training = False

    def get_client_id(self):
        return self.client_id

    def is_selected(self):
        return self.selected

    def failed_in_training(self):
        return self.failed_training

    def update_metrics(self, metrics : MetricsResponse):
        self.metrics.append(metrics)

    def get_metrics(self, round_id : int):
        return self.metrics[round_id]

    def update_training_response(self, training_response : TrainingResponse):
        self.training_response = training_response

    def get_training_response(self):
        return self.metrics
