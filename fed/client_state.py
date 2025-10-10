
class ClientState:
    def __init__(self, client_id ):
        self.client_id = client_id
        self.client_metric = {}
        self.selected = False
        self.failed_training = False

    def get_client_id(self):
        return self.client_id

    def was_selected_on_previous_round(self):
        return self.selected

    def failed_in_last_training(self):
        return self.failed_training

    def set_metric(self, metric, metric_value):
        self.client_metric[metric] = metric_value

    def get_metric(self, metric):
        return self.client_metric[metric]
