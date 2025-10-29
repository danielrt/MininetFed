from abc import abstractmethod

from numpy import ndarray

from fed.client_metrics import ClientMetrics


class Client:
    def __init__(self):
        pass

    @abstractmethod
    def split_data(self, path_to_data : str):
        pass

    @abstractmethod
    def fit(self, list[ndarray]) -> bool:
        pass

    @abstractmethod
    def eval(self) -> ClientMetrics:
        pass

    def get_weights(self) -> list[ndarray]:
        pass