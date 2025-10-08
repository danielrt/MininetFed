import numpy as np
from numpy import ndarray

from fed.aggregators.aggregator import Aggregator
from fed.training_response import TrainingResponse

class FedAvg(Aggregator):
    def aggregate(self, training_responses: dict[str, TrainingResponse]) -> list[ndarray]:
        all_trainer_samples = []
        all_weights = []
        for client_id in training_responses:
            all_trainer_samples.append(
                training_responses[client_id].num_samples)
            all_weights.append(training_responses[client_id].weights)

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