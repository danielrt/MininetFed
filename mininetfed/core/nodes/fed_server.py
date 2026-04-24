import logging
import time

import numpy as np
from numpy import ndarray
import json
import csv
import os

from mininetfed.core.fed_options import ServerOptions, AggregatorType, ClientSelectorType, \
    ClientAcceptorType
from mininetfed.core.metric_aggregators.global_metrics_aggregator import GlobalMetricsAggregator
from mininetfed.core.model_aggregators.fedavg import FedAvg
from mininetfed.core.client_acceptors.all_clients_acceptor import AllClientsAcceptor
from mininetfed.core.dto.client_info import ClientInfo
from mininetfed.core.client_selectors.all_clients_selector import AllClientsSelector
from mininetfed.core.dto.client_state import ClientState
from mininetfed.core.nodes.fed_node import FedNode, FedTopics
from mininetfed.core.dto.metrics import Metrics, MetricType
from mininetfed.core.dto.training_data import TrainingData
from mininetfed.core.dto.dataset_info import DatasetInfo
from mininetfed.core.utils import Color


def save_weights(path, weights: list[ndarray]):
    """
    Salva pesos agregados do modelo global (lista de ndarrays) como NPZ.
    """
    #path = os.path.join(super().get_node_folder(), f"model_{self.current_round}.npz")
    payload = {f"p{i}": w for i, w in enumerate(weights)}
    np.savez_compressed(path, **payload)

class FedServer(FedNode):
    def __init__(self):
        super().__init__()
        self.best_model_file = ""
        self.last_model_file = ""
        self.metrics_summary_file = ""
        self.learning_curve_file = ""
        self.learning_curve_rows: list[dict] = []

        self.fed_clients: dict[str, ClientState] = {}
        self.training_responses: list[TrainingData] = []
        self.metrics_responses: list[Metrics] = []
        self.current_round = 0
        self.agg_metrics_by_round : list[Metrics] = []
        self.best_metrics : Metrics | None = None
        self.best_target_metric = 0.0
        self.target_metric_stop_value = 0.0
        self.target_metric = MetricType.ACCURACY
        self.model_aggregator = AggregatorType.FED_AVG
        self.client_selector = ClientSelectorType.ALL_CLIENTS
        self.client_acceptor = ClientAcceptorType.ALL_CLIENTS
        self.no_improvement_counter = 0
        self.last_model : TrainingData | None = None
        self.best_model : TrainingData | None = None
        self.server_args = None
        self.num_rounds = 0
        self.min_trainers = 0

        # general logger
        self.logger = logging.getLogger("server")
        self.logger.setLevel(logging.INFO)

        # spnfl logger (https://sol.sbc.org.br/index.php/sbrc/article/view/35122/34913)
        self.spnfl_logger = logging.getLogger("spnfl")
        self.spnfl_logger.setLevel(logging.INFO)
        self.spnfl_logger.propagate = False

    def _safe_get_metric(self, metrics: Metrics, metric_name: str, default=None):
        try:
            return metrics.get_metric(metric_name)
        except Exception:
            return default

    def _append_learning_curve_row(
            self,
            round_id: int,
            agg_metrics: Metrics,
            n_selected_clients: int,
            n_metric_responses: int,
            round_duration: float,
    ):
        row = {
            "round": round_id,
            "accuracy": self._safe_get_metric(agg_metrics, MetricType.ACCURACY),
            "precision": self._safe_get_metric(agg_metrics, MetricType.PRECISION),
            "recall": self._safe_get_metric(agg_metrics, MetricType.RECALL),
            "f1": self._safe_get_metric(agg_metrics, MetricType.F1),
            "weighted_precision": self._safe_get_metric(agg_metrics, MetricType.WEIGHTED_PRECISION),
            "weighted_recall": self._safe_get_metric(agg_metrics, MetricType.WEIGHTED_RECALL),
            "weighted_f1": self._safe_get_metric(agg_metrics, MetricType.WEIGHTED_F1),
            "micro_precision": self._safe_get_metric(agg_metrics, MetricType.MICRO_PRECISION),
            "micro_recall": self._safe_get_metric(agg_metrics, MetricType.MICRO_RECALL),
            "micro_f1": self._safe_get_metric(agg_metrics, MetricType.MICRO_F1),
            "n_selected_clients": n_selected_clients,
            "n_metric_responses": n_metric_responses,
            "round_duration_sec": round_duration,
        }
        self.learning_curve_rows.append(row)

    def save_learning_curve_csv(self):
        if not self.learning_curve_rows:
            self.logger.warning("No learning curve rows to save.")
            return

        fieldnames = list(self.learning_curve_rows[0].keys())

        with open(self.learning_curve_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.learning_curve_rows)

        self.logger.info(f"Learning curve CSV saved to {self.learning_curve_file}")
        print(f"Learning curve CSV saved to {self.learning_curve_file}")

    def get_topics_to_subscribe(self) -> list[FedTopics]:
        return [FedTopics.CLIENT_REGISTER, FedTopics.CLIENT_READY,
                  FedTopics.CLIENT_WEIGHTS, FedTopics.CLIENT_METRICS]

    def configure(self, server_id, broker_addr, server_folder, server_args : dict):
        super().configure(server_id, broker_addr, server_folder, server_args)

        self.best_model_file = f'{server_folder}/best.model'
        self.last_model_file = f'{server_folder}/last.model'
        self.metrics_summary_file = f'{server_folder}/metrics_summary.txt'
        self.learning_curve_file = f'{server_folder}/learning_curve.csv'
        self.server_args = server_args

        required = {ServerOptions.MIN_CLIENTS, ServerOptions.NUM_ROUNDS, ServerOptions.STOP_VALUE}
        missing = required - server_args.keys()
        if missing:
            raise RuntimeError(f"The following server configurations should be provided: {missing}")
        else:
            self.num_rounds = server_args[ServerOptions.NUM_ROUNDS]
            self.min_trainers = server_args[ServerOptions.MIN_CLIENTS]
            self.target_metric_stop_value = server_args[ServerOptions.STOP_VALUE]

        # optional server args
        if ServerOptions.TARGET_METRIC in server_args:
            self.target_metric = server_args[ServerOptions.TARGET_METRIC]
        if ServerOptions.MODEL_AGGREGATOR in server_args:
            self.model_aggregator = server_args[ServerOptions.MODEL_AGGREGATOR]
        if ServerOptions.CLIENT_ACCEPTOR in server_args:
            self.client_acceptor = server_args[ServerOptions.CLIENT_ACCEPTOR]
        if ServerOptions.CLIENT_SELECTOR in server_args:
            self.client_selector = server_args[ServerOptions.CLIENT_SELECTOR]

        # general logger
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
        log_file = f'{server_folder}/server.log'
        h_general = logging.FileHandler(filename=log_file, mode="w")
        h_general.setFormatter(logging.Formatter(log_format))
        self.logger.addHandler(h_general)

        # spnfl logger (https://sol.sbc.org.br/index.php/sbrc/article/view/35122/34913)
        spnfl_log_file = f'{server_folder}/spn.log'
        spnfl_format_logger = "%(asctime)s - %(message)s"
        h_spnfl = logging.FileHandler(spnfl_log_file, mode="w")
        h_spnfl.setFormatter(logging.Formatter(spnfl_format_logger))
        self.spnfl_logger.addHandler(h_spnfl)

    def on_client_register(self, message):
        client_info = ClientInfo.from_json(message.payload.decode("utf-8"))
        accepted = self.accept_client(client_info)
        client_id = client_info.get_client_id()
        if accepted:
            self.fed_clients[client_id] = ClientState(client_id)
            self.fed_clients[client_id].set_client_info(client_info)
            self.logger.info(
                f'client {client_id} was accepted to join the pool')
            print(
                f'client {client_id} was accepted to join the pool')
        else:
            self.logger.info(
                f'client {client_id} was denied to join the pool')
            print(
                f'client {client_id} was denied to join the pool')

        super().publish_to(
            FedTopics.CLIENT_ACCEPTED, json.dumps({"client_id": client_id, "accepted": accepted}))

    def on_client_ready(self, message):
        data_info = DatasetInfo.from_json(message.payload.decode("utf-8"))
        client_id = data_info.get_client_id()
        self.fed_clients[client_id].set_dataset_info(data_info)
        self.spnfl_logger.info(f'T_ARRIVAL {client_id}')

    # callback for preAggQueue: get weights of trainers, aggregate and send back
    def on_client_weights(self, message):
        training_response = TrainingData.from_json(message.payload.decode("utf-8"))
        client_id = training_response.get_node_id()
        was_success = training_response.was_success()
        client_round_id = training_response.get_round_id()
        response_status = was_success and client_round_id == self.current_round
        print(f"[SERVER] CLIENT_WEIGHTS from {client_id}")
        self.fed_clients[client_id].set_training_status_for_round(self.current_round, response_status)
        self.spnfl_logger.info(f'T_RETURN_0 {client_id} {was_success}')
        if response_status:
            self.training_responses.append(training_response)
            self.fed_clients[client_id].set_training_status_for_round(client_round_id, True)
            self.logger.info(
                f'received weights from trainer {client_id}!')
            print(f'received weights from trainer {client_id}!')
        else:
            self.fed_clients[client_id].set_training_status_for_round(client_round_id, False)
            print(f'client {client_id} failed in training or delivered response too late!')

    # callback for metricsQueue: get the metrics from each client after it finish its round
    def on_client_metrics(self, message):
        metric_response = Metrics.from_json(message.payload.decode("utf-8"))
        self.metrics_responses.append(metric_response)
        self.fed_clients[metric_response.client_id].set_metrics_for_round(self.current_round, metric_response)
        self.spnfl_logger.info(f'T_RETURN_1 {metric_response.get_client_id()}')

    def accept_client(self, client_info : ClientInfo) -> bool:
        accepted_clients = None
        if self.client_acceptor == ClientAcceptorType.ALL_CLIENTS:
            accepted_clients = AllClientsAcceptor().accept(client_info)
        return accepted_clients

    def select_clients(self, clients_states : list[ClientState]) -> list[str]:
        selected_clients = None
        if self.client_selector == ClientSelectorType.ALL_CLIENTS:
            selected_clients = AllClientsSelector().select_clients(clients_states)
        return selected_clients

    def aggregate_model(self, training_responses : list[TrainingData], clients_state : dict[str, ClientState]) -> list[ndarray]:
        agg_model = None
        if self.model_aggregator == AggregatorType.FED_AVG:
            agg_model = FedAvg().aggregate(training_responses, clients_state)
        return agg_model

    def aggregate_metrics(self, clients_metrics : list[Metrics], n_samples : list[int]) -> Metrics:
        agg_metrics = GlobalMetricsAggregator().aggregate(clients_metrics, n_samples)
        self.agg_metrics_by_round.append(agg_metrics)
        return agg_metrics

    def stop_condition(self, agg_metrics : Metrics) -> bool:
        agg_target_metric = agg_metrics.get_metric(self.target_metric)
        self.logger.info(f'{self.target_metric}: {agg_target_metric}\n')
        print(Color.GREEN +
              f'{self.target_metric} on round {self.current_round} was {agg_target_metric}\n' + Color.RESET)
        if agg_target_metric >= self.target_metric_stop_value:
            print(Color.YELLOW + f'Stop condition by stop value was met' + Color.YELLOW)
            return True
        else:
            if agg_target_metric > self.best_target_metric:
                self.best_target_metric = agg_target_metric
                self.best_metrics = agg_metrics
                self.best_model = self.last_model
                self.no_improvement_counter = 0
            else:
                self.no_improvement_counter += 1
                print(Color.YELLOW + f'No improvements for {self.target_metric} occurred in the last {self.no_improvement_counter}' + Color.YELLOW)

                if ServerOptions.PATIENT in self.server_args:
                    if self.no_improvement_counter >= self.server_args[ServerOptions.PATIENT]:
                        print(Color.YELLOW + f'Stop condition by early stop was met' + Color.YELLOW)
                        return True
        return False

    def get_num_ready_clients(self) -> int:
        return sum(
            1 for c in self.fed_clients.values()
            if c.get_dataset_info() is not None
        )

    def run(self):
        super().start_communication_loop()

        # espera conexão
        if not self.wait_until_connected(timeout=5.0):
            print(f"[SERVER {self.get_node_id()}] Failed to connect/subscribe to broker")
            return

        self.logger.info(f'starting server {super().get_node_id()}...')
        print(Color.BOLD_START + f'starting node {super().get_node_id()}...' + Color.BOLD_END)

        self.spnfl_logger.info("INIT_EXPERIMENT")

        self.spnfl_logger.info("T_ARRIVAL_START")

        # wait trainers to connect
        # opcional: timeout
        max_wait = 60  # segundos
        t0 = time.time()

        # wait trainers to be READY
        while self.get_num_ready_clients() < self.min_trainers:
            if time.time() - t0 > max_wait:
                self.logger.warning(
                    f"Timeout waiting READY: only {self.get_num_ready_clients()} "
                    f"clients ready (min_trainers={self.min_trainers})"
                )
                super().publish_to(FedTopics.STOP, None)
                super().stop_communication_loop()
                return
            time.sleep(1)

        self.spnfl_logger.info(f'T_ARRIVAL_END {self.min_trainers} {len(self.fed_clients)}')

        # begin training
        round_times = []  # lista para armazenar o tempo de cada round
        stop_fed = False
        while self.current_round < self.num_rounds and not stop_fed:
            round_start_time = time.time()  # início do round
            self.training_responses = []
            self.metrics_responses = []
            self.logger.info(
                f'round: {self.current_round}')
            print(Color.RESET + '\n' + Color.BOLD_START +
                  f'starting round {self.current_round}' + Color.BOLD_END)

            self.spnfl_logger.info(f'START_ROUND {self.current_round}')

            self.spnfl_logger.info(f'T_SELECT_START')

            # select trainers for round
            if len(self.fed_clients) == 0:
                self.logger.critical("Client's list empty")

            all_fed_clients = list(self.fed_clients.values())
            selected_fed_clients = self.select_clients(all_fed_clients)

            self.logger.info(f"n_selected: {len(selected_fed_clients)}")
            self.logger.info(
                f"{json.dumps({'selected_trainers': selected_fed_clients})}")
            for fed_client in all_fed_clients:
                fed_client_id = fed_client.get_client_id()
                m_dict = {'id': fed_client_id, 'round_id' : self.current_round}

                if  fed_client_id in selected_fed_clients:
                    m_dict['selected'] = True
                    self.logger.info(f'selected: {fed_client_id}')
                    print(f'selected client {fed_client_id} for training on round {self.current_round}')
                    self.spnfl_logger.info(f'T_SELECT {fed_client_id} True')
                else:
                    m_dict['selected'] = False
                    self.logger.info(f'NOT_selected: {fed_client_id}')
                    self.spnfl_logger.info(f'T_SELECT {fed_client_id} False')

                super().publish_to(FedTopics.CLIENT_SELECTION, json.dumps(m_dict))

            self.spnfl_logger.info(f'T_SELECT_END {len(selected_fed_clients)}')

            self.spnfl_logger.info(f'T_RETURN_0_START')

            # wait for agg responses
            while len(self.training_responses) < len(selected_fed_clients):
                time.sleep(1)
            self.spnfl_logger.info(f'T_RETURN_0_END {len(self.training_responses)}')

            self.spnfl_logger.info(f'T_AGGREG_START')

            # aggregate and send
            agg_weights = self.aggregate_model(self.training_responses, self.fed_clients)

            self.last_model = TrainingData(super().get_node_id(), True, self.current_round, agg_weights)

            self.spnfl_logger.info(f'T_AGGREG_END')

            super().publish_to(FedTopics.SERVER_WEIGHTS, self.last_model.to_json())  #### T_SEND

            self.spnfl_logger.info(f'T_SEND')

            self.logger.info(f'sent aggregated weights to trainers!')
            print(f'sent aggregated weights to trainers and waiting trainers metrics!')

            self.spnfl_logger.info(f'T_RETURN_1_START')

            # wait for metrics response
            while len(self.metrics_responses) < len(selected_fed_clients):
                time.sleep(1)
            self.spnfl_logger.info(f'T_RETURN_1_END {len(self.metrics_responses)}')

            clients_metrics = []
            clients_n_samples = []
            for cid in selected_fed_clients:
                st = self.fed_clients[cid]
                m = st.get_metrics_for_round(self.current_round)
                if m is not None:
                    clients_metrics.append(m)
                    clients_n_samples.append(st.get_dataset_info().get_num_samples())

            agg_metrics = self.aggregate_metrics(clients_metrics, clients_n_samples)
            # spnfl_logger.info(f'T_COMPUTE_START')

            stop_fed = self.stop_condition(agg_metrics)


            self.spnfl_logger.info(f'T_SAVE_START')
            # TODO: salvar metadados do treinamento para poder fazer resume
            #with open(self.last_model_file, "w", encoding="utf-8") as f:
                #f.write(self.last_model.to_json())
            save_weights(self.last_model_file, self.last_model.get_weights())

            self.spnfl_logger.info(f'T_SAVE_END')

            if stop_fed:
                self.spnfl_logger.info(f'T_SAVE_START')
                # para o caso em que o modelo converge ja no round 0
                if not self.best_model:
                    self.best_model = self.last_model
                    self.best_metrics = self.agg_metrics_by_round[self.current_round]
                # TODO: salvar metadados do treinamento para poder fazer resume
                #with open(self.best_model_file, "w", encoding="utf-8") as f:
                #    f.write(self.best_model.to_json())
                save_weights(self.best_model_file, self.best_model.get_weights())
                self.best_metrics.save_summary(self.metrics_summary_file)
                self.spnfl_logger.info(f'T_SAVE_END')

            # calcular tempo do round e estimar tempo restante
            round_end_time = time.time()
            round_duration = round_end_time - round_start_time
            round_times.append(round_duration)

            self._append_learning_curve_row(
                round_id=self.current_round,
                agg_metrics=agg_metrics,
                n_selected_clients=len(selected_fed_clients),
                n_metric_responses=len(clients_metrics),
                round_duration=round_duration,
            )

            rounds_left = self.num_rounds - self.current_round
            if self.current_round > 0 and rounds_left > 0:
                avg_time = sum(round_times) / len(round_times)
                est_remaining = avg_time * rounds_left
                mins, secs = divmod(int(est_remaining), 60)
                print(
                    Color.BLUE + f"Estimated time remaining until the end of the experiment: {mins}m {secs}s" + Color.RESET)

            self.spnfl_logger.info(f'ROUND_DURATION {round_duration}')
            self.spnfl_logger.info(f'END_ROUND {self.current_round}')

            self.current_round += 1

        self.logger.info('stop condition was met')
        self.logger.info(f'{self.current_round} rounds were executed')
        print(Color.RED + f'stop condition was met!' + Color.RED)
        print(Color.YELLOW + f'{self.current_round} rounds were executed' + Color.YELLOW)

        self.save_learning_curve_csv()

        super().publish_to(FedTopics.STOP, None)
        super().stop_communication_loop()