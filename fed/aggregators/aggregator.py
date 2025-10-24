from abc import abstractmethod

from numpy import ndarray

from fed.client_training_data import ClientTrainingData


class Aggregator:

    @abstractmethod
    def aggregate(self, training_responses : dict[str, ClientTrainingData]) -> list[ndarray]:
        pass