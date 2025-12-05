from abc import abstractmethod

from numpy import ndarray

from mininetfed.core.dto.client_state import ClientState
from mininetfed.core.dto.training_data import TrainingData

class Aggregator:

    @abstractmethod
    def aggregate(self, training_responses : list[TrainingData], clients_state : dict[str, ClientState]) -> list[ndarray]:
        pass