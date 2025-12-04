import numpy as np
from numpy import ndarray

from mininetfed.core.model_aggregators.aggregator import Aggregator
from mininetfed.core.dto.client_state import ClientState
from mininetfed.core.dto.training_data import TrainingData

class FedAvg(Aggregator):
    def aggregate(self, training_responses: list[TrainingData], clients_state : dict[str, ClientState]) -> list[ndarray]:
        all_trainer_samples = []
        all_weights = []
        for training_response in training_responses:
            client_id = training_response.get_node_id()
            num_samples = clients_state[client_id].get_dataset_info().get_num_samples()
            all_trainer_samples.append(num_samples)
            all_weights.append(training_response.get_weights())

        scaling_factor = list(np.array(all_trainer_samples) /
                              np.array(all_trainer_samples).sum())

        # scale weights
        for scaling, weights in zip(scaling_factor, all_weights):
            for i in range(0, len(weights)):
                weights[i] = weights[i] * scaling

        # agg weights
        agg_weights = []
        for layer in range(0, len(all_weights[0])):
            var = []
            for model in range(0, len(all_weights)):
                var.append(all_weights[model][layer])
            agg_weights.append(sum(var))

        return agg_weights