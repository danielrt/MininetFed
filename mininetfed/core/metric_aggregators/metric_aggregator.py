from abc import abstractmethod

from mininetfed.core.dto.metrics import Metrics


class MetricAggregator:
    @abstractmethod
    def aggregate(self, clients_metrics : list[Metrics]) -> float:
        pass