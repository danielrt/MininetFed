import logging
import time
from numpy import ndarray
import json

from fed.client_acceptors.client_acceptor import ClientAcceptorType
from fed.client_selectors.client_selector import ClientSelectorType
from fed.metric_aggregators.accuracy_aggregator import AccuracyAggregator
from fed.model_aggregators.fedavg import FedAvg
from fed.client_acceptors.all_clients_acceptor import AllClientsAcceptor
from fed.client_info import ClientInfo
from fed.client_selectors.all_clients_selector import AllClientsSelector
from fed.client_state import ClientState
from fed.fed_node import FedNode, FedTopics
from fed.metrics import Metrics, MetricType
from fed.model_aggregators.model_aggregator import ModelAggregatorType
from fed.training_data import TrainingData
from fed.dataset_info import DatasetInfo
from fed.utils import Color


class FedServer(FedNode):
    def __init__(self):
        super().__init__()
        self.best_model_file = ""
        self.last_model_file = ""

        self.fed_clients: dict[str, ClientState] = {}
        self.training_responses: list[TrainingData] = []
        self.metrics_responses: list[Metrics] = []
        self.current_round = 1
        self.agg_metric_by_round = []
        self.best_agg_metric = 0.0
        self.metric_stop_value = 0.0
        self.metric_name = MetricType.ACCURACY
        self.model_aggregator = ModelAggregatorType.FED_AVG
        self.client_selector = ClientSelectorType.ALL_CLIENTS
        self.client_acceptor = ClientAcceptorType.ALL_CLIENTS
        self.no_improvement_counter = 0
        self.last_model = None
        self.best_model = None
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

    def get_topics_to_subscribe(self) -> list[FedTopics]:
        return [FedTopics.CLIENT_REGISTER, FedTopics.CLIENT_READY,
                  FedTopics.CLIENT_WEIGHTS, FedTopics.CLIENT_METRICS]

    def configure(self, server_id, broker_addr, server_folder, server_args : dict):
        super().configure(server_id, broker_addr, server_folder, server_args)

        self.best_model_file = f'{server_folder}/best.model'
        self.server_args = server_args

        required = {"min_trainers", "num_rounds", "stop_value", "metric_type"}
        missing = required - server_args.keys()
        if missing:
            raise RuntimeError(f"The following server configurations should be provided: {missing}")
        else:
            self.num_rounds = server_args["num_rounds"]
            self.min_trainers = server_args["min_trainers"]
            self.metric_stop_value = server_args["stop_value"]

        # optional server args
        if "metric_name" in server_args:
            self.metric_name = server_args["metric_name"]
        if "model_aggregator" in server_args:
            self.model_aggregator = server_args["model_aggregator"]
        if "client_acceptor" in server_args:
            self.client_acceptor = server_args["client_acceptor"]
        if "client_selector" in server_args:
            self.client_selector = server_args["client_selector"]

        # general logger
        log_format = "%(asctime)s - %(infotype)-6s - %(levelname)s - %(message)s"
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
        if self.model_aggregator == ModelAggregatorType.FED_AVG:
            agg_model = FedAvg().aggregate(training_responses, clients_state)
        return agg_model

    def aggregate_metrics(self, clients_metrics : list[Metrics]) -> float:
        agg_metric = 0.0
        if self.metric_name == MetricType.ACCURACY:
            agg_metric = AccuracyAggregator().aggregate(clients_metrics)
        return agg_metric

    def stop_condition(self, agg_metric : float) -> bool:
        self.logger.info(f'{self.metric_name}: {agg_metric}\n')
        print(Color.GREEN +
              f'{self.metric_name} on round {self.current_round} was {agg_metric}\n' + Color.RESET)
        self.agg_metric_by_round.append(agg_metric)
        if agg_metric >= self.metric_stop_value:
            return True
        else:
            if agg_metric >= self.best_agg_metric:
                self.best_agg_metric = agg_metric
                self.best_model = self.last_model
            else:
                self.no_improvement_counter += 1
                if "early_stop" in self.server_args:
                    if self.no_improvement_counter >= self.server_args["early_stop"]:
                        return True
        return False

    def run(self):
        super().start_communication_loop()
        self.logger.info(f'starting server {super().get_node_id()}...')
        print(Color.BOLD_START + f'starting node {super().get_node_id()}...' + Color.BOLD_END)
        #super().publish_to('minifed/autoWaitContinue', json.dumps({'continue': True}))

        self.spnfl_logger.info("INIT_EXPERIMENT")

        # best model so far
        best_model = None

        self.spnfl_logger.info("T_ARRIVAL_START")

        # wait trainers to connect
        while len(self.fed_clients) < self.min_trainers:
            time.sleep(1)

        self.spnfl_logger.info(f'T_ARRIVAL_END {self.min_trainers} {len(self.fed_clients)}')

        # begin training
        selected_qtd = 0
        round_times = []  # lista para armazenar o tempo de cada round
        stop_fed = False
        while self.current_round <= self.num_rounds and not stop_fed:
            round_start_time = time.time()  # início do round
            self.current_round += 1
            self.training_responses = []
            self.metrics_responses = []
            self.logger.info(
                f'round: {self.current_round}')
            print(Color.RESET + '\n' + Color.BOLD_START +
                  f'starting round {self.current_round}' + Color.BOLD_END)

            self.spnfl_logger.info(f'START_ROUND {self.current_round - 1}')

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
            while len(self.training_responses) < selected_qtd:
                time.sleep(1)
            self.spnfl_logger.info(f'T_RETURN_0_END {len(self.training_responses)}')

            self.spnfl_logger.info(f'T_AGGREG_START')

            # aggregate and send
            self.last_model = self.aggregate_model(self.training_responses, self.fed_clients)

            agg_model_data = TrainingData(super().get_node_id(), True, self.current_round, self.last_model)

            # save partial model here

            response = json.dumps(agg_model_data.to_json())

            self.spnfl_logger.info(f'T_AGGREG_END')

            super().publish_to(FedTopics.SERVER_WEIGHTS, response)  #### T_SEND

            self.spnfl_logger.info(f'T_SEND')

            self.logger.info(f'sent aggregated weights to trainers!')
            print(f'sent aggregated weights to trainers and waiting trainers metrics!')

            self.spnfl_logger.info(f'T_RETURN_1_START')

            # wait for metrics response
            while len(self.metrics_responses) < len(selected_fed_clients):
                time.sleep(1)
            self.spnfl_logger.info(f'T_RETURN_1_END {len(self.metrics_responses)}')

            clients_metrics = []
            for fed_client in self.fed_clients.values():
                clients_metrics.append(fed_client.get_metrics_for_round(self.current_round))

            agg_metric = self.aggregate_metrics(clients_metrics)
            # spnfl_logger.info(f'T_COMPUTE_START')

            stop_fed = self.stop_condition(agg_metric)

            self.spnfl_logger.info(f'T_SAVE_START')
            with open(self.last_model_file, "w", encoding="utf-8") as f:
                json.dump(self.last_model, f, ensure_ascii=False, indent=2)
            self.spnfl_logger.info(f'T_SAVE_END')

            if stop_fed:
                self.spnfl_logger.info(f'T_SAVE_START')
                with open(self.best_model_file, "w", encoding="utf-8") as f:
                    json.dump(self.best_model, f, ensure_ascii=False, indent=2)
                self.spnfl_logger.info(f'T_SAVE_END')

            # calcular tempo do round e estimar tempo restante
            round_end_time = time.time()
            round_duration = round_end_time - round_start_time
            round_times.append(round_duration)
            rounds_left = self.num_rounds - self.current_round
            if self.current_round > 0 and rounds_left > 0:
                avg_time = sum(round_times) / len(round_times)
                est_remaining = avg_time * rounds_left
                mins, secs = divmod(int(est_remaining), 60)
                print(
                    Color.BLUE + f"Estimated time remaining until the end of the experiment: {mins}m {secs}s" + Color.RESET)

            self.spnfl_logger.info(f'ROUND_DURATION {round_duration}')
            self.spnfl_logger.info(f'END_ROUND {self.current_round}')

        self.logger.info('stop condition was met')
        self.logger.info(f'{self.current_round} rounds were executed')
        print(Color.RED + f'stop condition was met!' + Color.RED)
        print(Color.YELLOW + f'{self.current_round} rounds were executed' + Color.YELLOW)
        super().publish_to(FedTopics.STOP, None)
        super().stop_communication_loop()