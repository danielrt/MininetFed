from abc import abstractmethod

from numpy import ndarray

from fed.training_response import TrainingResponse


class Aggregator:

    @abstractmethod
    def aggregate(self, training_responses : dict[str, TrainingResponse]) -> list[ndarray]:
        pass