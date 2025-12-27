import json

import numpy as np

from mininetfed.core.utils import JSONSerializableType

class MetricType:
    ACCURACY = "accuracy"
    CONFUSION_MATRIX = "confusion_matrix"
    F1 = "f1"
    RECALL = "recall"
    PRECISION = "precision"
    WEIGHTED_PRECISION = "weighted_precision"
    WEIGHTED_RECALL = "weighted_recall"
    WEIGHTED_F1 = "weighted_f1"
    MICRO_F1 = "micro_f1"
    MICRO_RECALL = "micro_recall"
    MICRO_PRECISION = "micro_precision"
    SUPPORT_PER_CLASS = "support_per_class"
    PRECISION_PER_CLASS = "precision_per_class"
    RECALL_PER_CLASS = "recall_per_class"
    F1_PER_CLASS = "f1_per_class"

class Metrics:
    def __init__(self, client_id : str, metrics : dict[str, JSONSerializableType]):
        self.client_id = client_id
        self.metrics = metrics

    @classmethod
    def from_json(cls, json_str : str) -> "Metrics":
        json_data = json.loads(json_str)
        client_id = json_data["client_id"]
        metrics = json_data["metrics"]
        return cls(client_id=client_id, metrics=metrics)

    def to_json(self) -> str:
        return json.dumps({"client_id": self.client_id, "metrics": self.metrics})

    def get_client_id(self) -> str:
        return self.client_id

    def get_all_metrics(self) -> dict[str, JSONSerializableType]:
        return self.metrics

    def get_metric(self, metric_name : str) -> JSONSerializableType:
        return self.metrics[metric_name]

    def save_summary(self, filepath: str, class_names: list[str] | None = None):
        float_fmt: str = "{:.4f}"

        m = self.metrics

        def fmt(x):
            if isinstance(x, float):
                return float_fmt.format(x)
            return str(x)

        with open(filepath, "w", encoding="utf-8") as f:
            # --------------------------------------------------
            # Cabeçalho
            # --------------------------------------------------
            f.write("=" * 60 + "\n")
            f.write(f"METRICS REPORT — CLIENT: {self.get_client_id()}\n")
            f.write("=" * 60 + "\n\n")

            # --------------------------------------------------
            # Métricas globais escalares
            # --------------------------------------------------
            f.write("[ GLOBAL METRICS ]\n")

            scalar_keys = [
                MetricType.ACCURACY,
                MetricType.PRECISION,
                MetricType.RECALL,
                MetricType.F1,
                MetricType.WEIGHTED_PRECISION,
                MetricType.WEIGHTED_RECALL,
                MetricType.WEIGHTED_F1,
                MetricType.MICRO_PRECISION,
                MetricType.MICRO_RECALL,
                MetricType.MICRO_F1,
            ]

            for k in scalar_keys:
                if k in m:
                    f.write(f"- {k:20s}: {fmt(m[k])}\n")

            f.write("\n")

            # --------------------------------------------------
            # Métricas por classe
            # --------------------------------------------------
            per_class_blocks = [
                (MetricType.SUPPORT_PER_CLASS, "Support"),
                (MetricType.PRECISION_PER_CLASS, "Precision"),
                (MetricType.RECALL_PER_CLASS, "Recall"),
                (MetricType.F1_PER_CLASS, "F1-score"),
            ]

            if any(k in m for k, _ in per_class_blocks):
                f.write("[ PER-CLASS METRICS ]\n")

                support = m.get(MetricType.SUPPORT_PER_CLASS)

                for key, title in per_class_blocks:
                    if key not in m:
                        continue

                    values = m[key]
                    f.write(f"{title}:\n")

                    for i, v in enumerate(values):
                        cname = (
                            class_names[i]
                            if class_names is not None and i < len(class_names)
                            else f"class_{i}"
                        )
                        if key == MetricType.SUPPORT_PER_CLASS:
                            f.write(f"  - {cname:15s}: {int(v)}\n")
                        else:
                            f.write(f"  - {cname:15s}: {fmt(v)}\n")

                    f.write("\n")

            # --------------------------------------------------
            # Matriz de confusão
            # --------------------------------------------------
            if MetricType.CONFUSION_MATRIX in m:
                f.write("[ CONFUSION MATRIX ]\n")

                cm = np.asarray(m[MetricType.CONFUSION_MATRIX], dtype=int)
                n_classes = cm.shape[0]

                # header
                f.write(" " * 15)
                for j in range(n_classes):
                    cname = (
                        class_names[j]
                        if class_names is not None and j < len(class_names)
                        else f"pred_{j}"
                    )
                    f.write(f"{cname:>10s}")
                f.write("\n")

                # rows
                for i in range(n_classes):
                    rname = (
                        class_names[i]
                        if class_names is not None and i < len(class_names)
                        else f"true_{i}"
                    )
                    f.write(f"{rname:15s}")
                    for j in range(n_classes):
                        f.write(f"{cm[i, j]:10d}")
                    f.write("\n")

                f.write("\n")

            # --------------------------------------------------
            # Estratégia (se existir)
            # --------------------------------------------------
            if "_strategy" in m:
                f.write("[ AGGREGATION STRATEGY ]\n")
                for k, v in m["_strategy"].items():
                    f.write(f"- {k}: {v}\n")

            f.write("\n")
            f.write("=" * 60 + "\n")
