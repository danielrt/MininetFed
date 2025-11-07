import numpy as np

from fed.metrics import Metrics, MetricType
from fed.metric_aggregators.metric_aggregator import MetricAggregator

class AccuracyAggregator(MetricAggregator):
    def aggregate(self, clients_metrics: list[Metrics]) -> float:
        accuracies = []
        for client_metrics in clients_metrics:
            accuracies.append(client_metrics.get_metric(MetricType.ACCURACY))
        mean_acc = float(np.mean(np.array(accuracies)))
        return mean_acc