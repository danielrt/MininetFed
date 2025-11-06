from abc import abstractmethod

from numpy import ndarray

from fed.client_state import ClientState
from fed.training_data import TrainingData

class ModelAggregatorType:
    FED_AVG = "fed_avg"

class ModelAggregator:

    @abstractmethod
    def aggregate(self, training_responses : list[TrainingData], clients_state : dict[str, ClientState]) -> list[ndarray]:
        pass