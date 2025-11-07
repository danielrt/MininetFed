from abc import abstractmethod

from fed.metrics import Metrics


class MetricAggregator:
    @abstractmethod
    def aggregate(self, clients_metrics : list[Metrics]) -> float:
        pass