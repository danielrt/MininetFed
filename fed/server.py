import logging
import time
from abc import abstractmethod
from typing import List

import numpy as np
from numpy import ndarray
import paho.mqtt.client as mqtt
import json

from fed.aggregators.fedavg import FedAvg
from fed.client_acceptors.all_clients_acceptor import AllClientsAcceptor
from fed.client_info import ClientInfo
from fed.client_selectors.all_clients_selector import AllClientsSelector
from fed.client_state import ClientState
from fed.metrics import Metrics, MetricType
from fed.training_data import TrainingData
from fed.dataset_info import DatasetInfo
from fed.utils import ndarray_to_base64


# class for coloring messages on terminal
class Color:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD_START = '\033[1m'
    BOLD_END = '\033[0m'
    RESET = "\x1B[0m"

class Server:
    def __init__(self):
        self.broker_addr = ""
        self.saved_model_file = ""

        self.fed_clients: dict[str, ClientState] = {}
        self.training_responses: list[TrainingData] = []
        self.metrics_responses: list[Metrics] = []
        self.current_round = 1
        self.accuracies_by_round = []
        self.best_acc = 0
        self.no_improvement_counter = 0
        self.last_model = None
        self.best_model = None
        self.server_args = None
        self.num_rounds = 0
        self.min_trainers = 0

        # connect on queue
        self.mqtt_client = None

        # general logger
        self.logger = logging.getLogger("server")
        self.logger.setLevel(logging.INFO)

        # spnfl logger (https://sol.sbc.org.br/index.php/sbrc/article/view/35122/34913)
        self.spnfl_logger = logging.getLogger("spnfl")
        self.spnfl_logger.setLevel(logging.INFO)
        self.spnfl_logger.propagate = False

        self.metricType = {"infotype": "METRIC"}
        self.executionType = {"infotype": "EXECUT"}

    @abstractmethod
    def configure(self):
        pass

    def configure_default(self, broker_addr, output_folder, server_args : dict):
        # connect on queue
        self.mqtt_client = mqtt.Client('server')
        self.mqtt_client.connect(broker_addr, bind_port=1883)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.message_callback_add('minifed/registerQueue', self.on_message_register)
        self.mqtt_client.message_callback_add('minifed/preAggQueue', self.on_message_agg)
        self.mqtt_client.message_callback_add('minifed/metricsQueue', self.on_message_metrics)

        self.saved_model_file = f'{output_folder}/best.model'

        # general logger
        log_format = "%(asctime)s - %(infotype)-6s - %(levelname)s - %(message)s"
        log_file = f'{output_folder}/server.log'
        h_general = logging.FileHandler(filename=log_file, mode="w")
        h_general.setFormatter(logging.Formatter(log_format))
        self.logger.addHandler(h_general)

        # spnfl logger (https://sol.sbc.org.br/index.php/sbrc/article/view/35122/34913)
        spnfl_log_file = f'{output_folder}/spn.log'
        spnfl_format_logger = "%(asctime)s - %(message)s"
        h_spnfl = logging.FileHandler(spnfl_log_file, mode="w")
        h_spnfl.setFormatter(logging.Formatter(spnfl_format_logger))
        self.spnfl_logger.addHandler(h_spnfl)

        self.server_args = server_args
        is_overridden = type(self).configure is not Server.configure
        required = {"min_trainers", "num_rounds", }
        if not is_overridden:
            required.add("stop_a")
        missing = required - server_args.keys()
        if missing:
            raise RuntimeError(f"The following server configurations should be provided: {missing}")
        else:
            self.num_rounds = server_args["num_rounds"]
            self.min_trainers = server_args["min_trainers"]

    # subscribe to queues on connection
    def on_connect(self, client, userdata, flags, rc):
        subscribe_queues = ['minifed/registerQueue', 'minifed/preAggQueue',
                            'minifed/metricsQueue', 'minifed/ready']
        for s in subscribe_queues:
            self.mqtt_client.subscribe(s)

    # callback for registerQueue: add trainer to the pool of trainers
    def on_message_ready(self, client, userdata, message):
        data_info = DatasetInfo.from_json(message.payload.decode("utf-8"))
        client_id = data_info.get_client_id()
        self.fed_clients[client_id].set_dataset_info(data_info)
        self.spnfl_logger.info(f'T_ARRIVAL {m["id"]}')

    def on_message_register(self, client, userdata, message):
        client_info = ClientInfo.from_json(message.payload.decode("utf-8"))
        accepted = self.accept_client(client_info)
        client_id = client_info.get_client_id()
        if accepted:
            self.fed_clients[client_id] = ClientState(client_id)
            self.fed_clients[client_id].set_client_info(client_info)
            self.logger.info(
                f'trainer {client_id} was accepted to join the pool', extra=self.executionType)
            print(
                f'trainer {client_id} was accepted to join the pool')
        else:
            self.logger.info(
                f'trainer {client_id} was denied to join the pool', extra=self.executionType)
            print(
                f'trainer number {client_id} was denied to join the pool')

        client.publish(
            'minifed/accept', json.dumps({"client_id": client_id, "accepted": accepted}))

    # callback for preAggQueue: get weights of trainers, aggregate and send back
    def on_message_agg(self, client, userdata, message):
        training_response = TrainingData.from_json(message.payload.decode("utf-8"))
        client_id = training_response.get_client_id()
        was_success = training_response.was_success()
        client_round_id = training_response.get_round_id()
        response_status = was_success and client_round_id == self.current_round
        self.fed_clients[client_id].set_training_status_for_round(self.current_round, response_status)
        self.spnfl_logger.info(f'T_RETURN_0 {client_id} {was_success}')
        if response_status:
            self.training_responses.append(training_response)
            self.fed_clients[client_id].set_training_status_for_round(client_round_id, True)
            self.logger.info(
                f'received weights from trainer {client_id}!', extra=self.executionType)
            print(f'received weights from trainer {client_id}!')
        else:
            self.fed_clients[client_id].set_training_status_for_round(client_round_id, False)
            print(f'client {client_id} failed in training or delivered response too late!')

    # callback for metricsQueue: get the metrics from each client after it finish its round
    def on_message_metrics(self, client, userdata, message):
        metric_response = Metrics.from_json(message.payload.decode("utf-8"))
        self.metrics_responses.append(metric_response)
        self.fed_clients[metric_response.client_id].set_metrics_for_round(self.current_round, metric_response)
        self.spnfl_logger.info(f'T_RETURN_1 {metric_response.get_client_id()}')

    def accept_client(self, client_info : ClientInfo) -> bool:
        return AllClientsAcceptor().accept(client_info)

    def select_clients(self, clients_states : list[ClientState]) -> list[str]:
        return AllClientsSelector().select_clients(clients_states)

    def aggregate(self, training_responses : list[TrainingData]) -> list[ndarray]:
        fed_avg = FedAvg()
        return fed_avg.aggregate(training_responses)

    def stop_condition(self, clients_metrics : list[Metrics]) -> bool:
        accuracies = []
        for client_metrics in clients_metrics:
            accuracies.append(client_metrics.get_metric(MetricType.ACCURACY))
        mean_acc = float(np.mean(np.array(accuracies)))
        self.logger.info(f'mean_accuracy: {mean_acc}\n', extra=self.metricType)
        print(Color.GREEN +
              f'mean accuracy on round {self.current_round} was {mean_acc}\n' + Color.RESET)
        self.accuracies_by_round.append(mean_acc)
        if "stop_acc" in self.server_args["stop_acc"]:
            stop_acc = self.server_args["stop_acc"]
            if mean_acc >= stop_acc:
                return True
            else:
                if mean_acc >= self.best_acc:
                    self.best_acc = mean_acc
                    self.best_model = self.last_model
                else:
                    self.no_improvement_counter += 1
                    if "early_stop" in self.server_args:
                        if self.no_improvement_counter >= self.server_args["early_stop"]:
                            return True
        return False

    def run(self):
        # start loop
        self.mqtt_client.loop_start()
        self.logger.info('starting server...', extra=self.executionType)
        print(Color.BOLD_START + 'starting server...' + Color.BOLD_END)
        self.mqtt_client.publish('minifed/autoWaitContinue', json.dumps({'continue': True}))

        self.spnfl_logger.info("INIT_EXPERIMENT")

        # best accuracy so far
        best_acc = 0
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
        while self.current_round <= self.num_rounds:
            round_start_time = time.time()  # início do round
            self.current_round += 1
            self.training_responses = []
            self.metrics_responses = []
            self.logger.info(
                f'round: {self.current_round}', extra=self.metricType)
            print(Color.RESET + '\n' + Color.BOLD_START +
                  f'starting round {self.current_round}' + Color.BOLD_END)

            self.spnfl_logger.info(f'START_ROUND {self.current_round - 1}')

            self.spnfl_logger.info(f'T_SELECT_START')

            # select trainers for round
            if len(self.fed_clients) == 0:
                self.logger.critical("Client's list empty", extra=self.executionType)

            all_fed_clients = list(self.fed_clients.values())
            selected_fed_clients = self.select_clients(all_fed_clients)

            self.logger.info(f"n_selected: {len(selected_fed_clients)}", extra=self.metricType)
            self.logger.info(
                f"{json.dumps({'selected_trainers': selected_fed_clients})}", extra=self.metricType)
            for fed_client in all_fed_clients:
                fed_client_id = fed_client.get_client_id()
                if  fed_client_id in selected_fed_clients:
                    # logger.info(
                    #     f'selected: {t}', extra=metricType)
                    print(
                        f'selected trainer {fed_client_id} for training on round {self.current_round}')
                    m = json.dumps({'id': fed_client_id, 'selected': True, 'round_id' : self.current_round}).replace(' ', '')
                    self.mqtt_client.publish('minifed/selectionQueue', m)
                    self.spnfl_logger.info(f'T_SELECT {fed_client_id} True')
                else:
                    # logger.info(
                    #     f'NOT_selected: {t}', extra=metricType)
                    m = json.dumps({'id': fed_client_id, 'selected': False, 'round_id' : self.current_round}).replace(' ', '')
                    self.mqtt_client.publish('minifed/selectionQueue', m)
                    self.spnfl_logger.info(f'T_SELECT {fed_client_id} False')

            self.spnfl_logger.info(f'T_SELECT_END {len(selected_fed_clients)}')

            self.spnfl_logger.info(f'T_RETURN_0_START')

            # wait for agg responses
            while len(self.training_responses) < selected_qtd:
                time.sleep(1)
            self.spnfl_logger.info(f'T_RETURN_0_END {len(self.training_responses)}')

            self.spnfl_logger.info(f'T_AGGREG_START')

            # aggregate and send
            self.last_model = self.aggregate(self.training_responses)

            # save partial model here

            response = json.dumps(ndarray_to_base64(self.last_model))

            self.spnfl_logger.info(f'T_AGGREG_END')

            self.mqtt_client.publish('minifed/posAggQueue', response)  #### T_SEND

            self.spnfl_logger.info(f'T_SEND')

            self.logger.info(f'sent aggregated weights to trainers!',
                        extra=self.executionType)
            print(f'sent aggregated weights to trainers and waiting trainers metrics!')

            self.spnfl_logger.info(f'T_RETURN_1_START')

            # wait for metrics response
            while len(self.metrics_responses) < len(selected_fed_clients):
                time.sleep(1)
            self.spnfl_logger.info(f'T_RETURN_1_END {len(self.metrics_responses)}')

            clients_metrics = []
            for fed_client in self.fed_clients.values():
                clients_metrics.append(fed_client.get_metrics_for_round(self.current_round))

            # spnfl_logger.info(f'T_COMPUTE_START')

            stop_fed = self.stop_condition(clients_metrics)

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

            #self.spnfl_logger.info(f'T_SAVE_START')
            #if mean_acc >= best_acc:
            #    best_model = controller.get_global_model()
            #    best_acc = mean_acc
            #self.spnfl_logger.info(f'T_SAVE_END')

            self.spnfl_logger.info(f'ROUND_DURATION {round_duration}')

            # update stop queue or continue process
            if stop_fed:
                with open(self.saved_model_file, "w", encoding="utf-8") as f:
                    json.dump(best_model, f, ensure_ascii=False, indent=2)
                # spnfl_logger.info(f'T_SAVE_END')

                self.logger.info('stop_condition: accuracy', extra=self.metricType)
                print(Color.RED + f'accuracy threshold met! stopping the training!')
                m = json.dumps({'stop': True})
                self.mqtt_client.publish('minifed/stopQueue', m)
                time.sleep(1)  # time for clients to finish
                # spnfl_logger.info(f'T_COMPUTE_END')
                self.spnfl_logger.info(f'END_ROUND {self.current_round}')
                exit()

            # spnfl_logger.info(f'T_SAVE_END')
            # spnfl_logger.info(f'T_COMPUTE_END')
            self.spnfl_logger.info(f'END_ROUND {self.current_round}')

        # spnfl_logger.info(f'T_SAVE_START')
        with open(self.saved_model_file, "w", encoding="utf-8") as f:
            json.dump(self.best_model, f, ensure_ascii=False, indent=2)
        # spnfl_logger.info(f'T_SAVE_END')

        self.logger.info('stop_condition: rounds', extra=self.metricType)
        print(Color.RED + f'rounds threshold met! stopping the training!' + Color.RESET)
        self.mqtt_client.publish('minifed/stopQueue', None)
        self.mqtt_client.loop_stop()