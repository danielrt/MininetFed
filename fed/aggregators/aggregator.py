from abc import abstractmethod

from numpy import ndarray

from fed.training_data import TrainingData


class Aggregator:

    @abstractmethod
    def aggregate(self, training_responses : list[TrainingData]) -> list[ndarray]:
        pass