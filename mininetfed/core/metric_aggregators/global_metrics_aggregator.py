from __future__ import annotations

from typing import Any, Optional
import numpy as np

from mininetfed.core.dto.metrics import Metrics, MetricType
from mininetfed.core.metric_aggregators.metric_aggregator import MetricAggregator


class GlobalMetricsAggregator(MetricAggregator):
    """
    Agregador global adaptativo:
    - Cliente precisa enviar ao menos UMA métrica (qualquer) no conjunto total do round.
    - Se houver 'confusion_matrix' em >=1 cliente, agrega CMs (soma) e deriva métricas globais.
    - Caso contrário, agrega métricas escalares por média ponderada (n_samples).
    - Também agrega métricas numéricas "custom" automaticamente.
    """

    def aggregate(self, clients_metrics: list[Metrics], n_samples: list[int]) -> Metrics:
        if len(clients_metrics) == 0:
            raise ValueError("clients_metrics vazio.")
        if len(n_samples) != len(clients_metrics):
            raise ValueError("n_samples precisa ter o mesmo tamanho de clients_metrics.")

        # pelo menos UMA métrica no total (entre todos os clientes)
        total_keys = 0
        for m in clients_metrics:
            if m is None:
                continue
            total_keys += len(m.get_all_metrics() or {})

        if total_keys == 0:
            raise ValueError("Nenhum cliente enviou métricas no round. Envie ao menos 1 métrica.")

        out: dict[str, Any] = {}

        # 1) Se houver confusion_matrix: agrega e deriva métricas
        global_cm = self._try_aggregate_confusion_matrix(clients_metrics)
        if global_cm is not None:
            out[MetricType.CONFUSION_MATRIX] = global_cm.tolist()  # JSON serializável

            derived = self._derive_metrics_from_confusion_matrix(global_cm)
            out.update(derived)

            out["_clients_with_cm"] = self._clients_with_key(clients_metrics, MetricType.CONFUSION_MATRIX)
            return Metrics(client_id="GLOBAL", metrics=out)

        # 2) Sem confusion_matrix: agrega o que existir (ponderado por n_samples)
        acc = self._weighted_mean_if_present(clients_metrics, n_samples, MetricType.ACCURACY)
        prec = self._weighted_mean_if_present(clients_metrics, n_samples, MetricType.PRECISION)
        rec = self._weighted_mean_if_present(clients_metrics, n_samples, MetricType.RECALL)
        f1 = self._weighted_mean_if_present(clients_metrics, n_samples, MetricType.F1)

        if acc is not None:
            out[MetricType.ACCURACY] = acc
        if prec is not None:
            out[MetricType.PRECISION] = prec
        if rec is not None:
            out[MetricType.RECALL] = rec
        if f1 is not None:
            out[MetricType.F1] = f1

        # agrega quaisquer outras métricas numéricas custom automaticamente
        other_agg = self._aggregate_other_numeric_metrics(
            clients_metrics,
            n_samples,
            exclude=set(out.keys()) | {MetricType.CONFUSION_MATRIX},
        )
        out.update(other_agg)

        if len(out) == 0:
            raise ValueError(
                "Clientes enviaram métricas, mas nenhuma foi agregável "
                f"(esperado: {MetricType.ACCURACY}/{MetricType.PRECISION}/{MetricType.RECALL}/{MetricType.F1} "
                f"ou {MetricType.CONFUSION_MATRIX}, ou métricas numéricas custom)."
            )

        return Metrics(client_id="GLOBAL", metrics=out)

    # -------------------------
    # Helpers
    # -------------------------
    def _clients_with_key(self, clients_metrics: list[Metrics], key: str) -> list[str]:
        ids = []
        for m in clients_metrics:
            if m is None:
                continue
            d = m.get_all_metrics() or {}
            if key in d:
                ids.append(m.get_client_id())
        return ids

    def _try_aggregate_confusion_matrix(self, clients_metrics: list[Metrics]) -> Optional[np.ndarray]:
        cms = []
        expected_shape = None

        for m in clients_metrics:
            if m is None:
                continue
            d = m.get_all_metrics() or {}
            cm = d.get(MetricType.CONFUSION_MATRIX, None)
            if cm is None:
                continue

            cm_np = np.asarray(cm, dtype=np.int64)

            if cm_np.ndim != 2 or cm_np.shape[0] != cm_np.shape[1]:
                raise ValueError(
                    f"Confusion matrix inválida do cliente {m.get_client_id()}: shape={cm_np.shape}, esperado (C,C)."
                )

            if expected_shape is None:
                expected_shape = cm_np.shape
            elif cm_np.shape != expected_shape:
                raise ValueError(
                    f"Clientes com confusion_matrix têm shapes diferentes: {cm_np.shape} != {expected_shape}. "
                    "Garanta mesma ordem/quantidade de classes."
                )

            cms.append(cm_np)

        if not cms:
            return None

        return np.sum(np.stack(cms, axis=0), axis=0)

    def _derive_metrics_from_confusion_matrix(self, cm: np.ndarray, eps: float = 1e-12) -> dict[str, Any]:
        total = float(np.sum(cm))
        acc = float(np.trace(cm) / (total + eps))

        tp = np.diag(cm).astype(np.float64)
        fp = np.sum(cm, axis=0).astype(np.float64) - tp
        fn = np.sum(cm, axis=1).astype(np.float64) - tp

        precision_per_class = tp / (tp + fp + eps)
        recall_per_class = tp / (tp + fn + eps)
        f1_per_class = (2.0 * precision_per_class * recall_per_class) / (precision_per_class + recall_per_class + eps)

        support = np.sum(cm, axis=1).astype(np.float64)
        w = support / (np.sum(support) + eps)

        # macro
        p_macro = float(np.mean(precision_per_class))
        r_macro = float(np.mean(recall_per_class))
        f1_macro = float(np.mean(f1_per_class))

        # weighted
        p_weighted = float(np.sum(precision_per_class * w))
        r_weighted = float(np.sum(recall_per_class * w))
        f1_weighted = float(np.sum(f1_per_class * w))

        # micro (single-label multiclass: micro = accuracy)
        tp_sum = float(np.sum(tp))
        p_micro = float(tp_sum / (total + eps))
        r_micro = float(tp_sum / (total + eps))
        f1_micro = float((2.0 * p_micro * r_micro) / (p_micro + r_micro + eps))

        return {
            MetricType.ACCURACY: acc,
            MetricType.PRECISION: p_macro,
            MetricType.RECALL: r_macro,
            MetricType.F1: f1_macro,

            MetricType.WEIGHTED_PRECISION: p_weighted,
            MetricType.WEIGHTED_RECALL: r_weighted,
            MetricType.WEIGHTED_F1: f1_weighted,

            MetricType.MICRO_PRECISION: p_micro,
            MetricType.MICRO_RECALL: r_micro,
            MetricType.MICRO_F1: f1_micro,

            MetricType.SUPPORT_PER_CLASS: support.astype(int).tolist(),
            MetricType.PRECISION_PER_CLASS: precision_per_class.tolist(),
            MetricType.RECALL_PER_CLASS: recall_per_class.tolist(),
            MetricType.F1_PER_CLASS: f1_per_class.tolist(),
        }

    def _weighted_mean_if_present(
        self,
        clients_metrics: list[Metrics],
        n_samples: list[int],
        key: str,
        eps: float = 1e-12
    ) -> Optional[float]:
        num = 0.0
        den = 0.0

        for m, n in zip(clients_metrics, n_samples):
            if m is None:
                continue
            d = m.get_all_metrics() or {}
            v = d.get(key, None)
            if v is None:
                continue
            if not isinstance(v, (int, float)):
                continue
            num += float(v) * float(n)
            den += float(n)

        if den == 0.0:
            return None
        return float(num / (den + eps))

    def _aggregate_other_numeric_metrics(
        self,
        clients_metrics: list[Metrics],
        n_samples: list[int],
        exclude: set[str],
        eps: float = 1e-12
    ) -> dict[str, float]:
        keys = set()
        for m in clients_metrics:
            if m is None:
                continue
            for k, v in (m.get_all_metrics() or {}).items():
                if k in exclude:
                    continue
                if isinstance(v, (int, float)):
                    keys.add(k)

        out: dict[str, float] = {}
        for k in keys:
            wm = self._weighted_mean_if_present(clients_metrics, n_samples, k, eps=eps)
            if wm is not None:
                out[k] = wm
        return out
