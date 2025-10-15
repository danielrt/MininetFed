import logging
import time
from abc import abstractmethod
from typing import List

import numpy as np
from numpy import ndarray
import paho.mqtt.client as mqtt
import json

from fed.aggregators.fedavg import FedAvg
from fed.client_selectors.all_clients_selector import AllClientsSelector
from fed.client_state import ClientState
from fed.metrics_response import MetricsResponse
from fed.training_response import TrainingResponse


# class for coloring messages on terminal
class color:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD_START = '\033[1m'
    BOLD_END = '\033[0m'
    RESET = "\x1B[0m"

class Server:
    def __init__(self, broker_addr, experiments_result_folder, **server_args):
        self.fed_clients : list[ClientState] = []

        # connect on queue
        self.mqtt_client = mqtt.Client('server')
        self.mqtt_client.connect(broker_addr, bind_port=1883)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.message_callback_add('minifed/registerQueue', self.on_message_register)
        self.mqtt_client.message_callback_add('minifed/preAggQueue', self.on_message_agg)
        self.mqtt_client.message_callback_add('minifed/metricsQueue', self.on_message_metrics)
        self.mqtt_client.message_callback_add('minifed/ready', self.on_message_ready)

        self.server_args = server_args
        self.broker_addr = broker_addr
        self.saved_model_file = f'{experiments_result_folder}/best.model'
        self.min_trainers = server_args["min_trainers"]
        self.nun_rounds = server_args["num_rounds"]
        self.stop_acc = server_args["stop_acc"]
        self.client_args = server_args.get("client")
        self.metricType = {"infotype": "METRIC"}
        self.executionType = {"infotype": "EXECUT"}

        self.current_round = 0

        FORMAT = "%(asctime)s - %(infotype)-6s - %(levelname)s - %(message)s"
        # logging.basicConfig(level=logging.INFO, filename=log_file,
        #                    format=FORMAT, filemode="w")
        # logger = logging.getLogger(__name__)

        # logger geral
        log_file = f'{experiments_result_folder}/server.log'
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        h_general = logging.FileHandler(filename=log_file, mode="w")
        h_general.setFormatter(logging.Formatter(FORMAT))
        self.logger.addHandler(h_general)

        # logger spnfl (artigo https://sol.sbc.org.br/index.php/sbrc/article/view/35122/34913)
        spnfl_log_file = f'{experiments_result_folder}/spn.log'
        FORMAT_SPNFL = "%(asctime)s - %(message)s"
        self.spnfl_logger = logging.getLogger("spnfl")
        self.spnfl_logger.setLevel(logging.INFO)
        self.spnfl_logger.propagate = False  # não manda para os handlers do "myapp"
        h_spnfl = logging.FileHandler(spnfl_log_file, mode="w")
        h_spnfl.setFormatter(logging.Formatter(FORMAT_SPNFL))
        self.spnfl_logger.addHandler(h_spnfl)



    # subscribe to queues on connection
    def on_connect(self, client, userdata, flags, rc):
        subscribe_queues = ['minifed/registerQueue', 'minifed/preAggQueue',
                            'minifed/metricsQueue', 'minifed/ready']
        for s in subscribe_queues:
            client.subscribe(s)

    # callback for registerQueue: add trainer to the pool of trainers
    def on_message_ready(self, client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))
        client_id = m['id']
        self.fed_clients.append(ClientState(client_id))

    def on_message_register(self, client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))
        metrics = MetricsResponse.from_json(m['metrics'])
        self.fed_clients[m['id']].update_metrics(metrics)
        self.logger.info(
            f'trainer number {m["id"]} just joined the pool', extra=self.executionType)
        print(
            f'trainer number {m["id"]} just joined the pool')

        client.publish(
            'minifed/serverArgs', json.dumps({"id": m["id"], "args": self.client_args}))

    # callback for preAggQueue: get weights of trainers, aggregate and send back
    def on_message_agg(self, client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))
        training_response = TrainingResponse(m["success"], m["weights"], m["num_samples"], m["training_args"])
        self.fed_clients[m['id']].update_training_response(training_response)

        self.spnfl_logger.info(f'T_RETURN_0 {m["id"]} {m["success"]}')
        if m['success']:
            self.logger.info(
                f'received weights from trainer {m["id"]}!', extra=self.executionType)
            print(f'received weights from trainer {m["id"]}!')
        else:
            print(f'client {m["id"]} failed in training!')



    # callback for metricsQueue: get the metrics from each client after it finish its round
    def on_message_metrics(self, client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))
        controller.add_accuracy(m['metrics']['accuracy'])
        controller.update_metrics(m["id"], m['metrics'])
        m["metrics"]["client_name"] = m["id"]
        self.logger.info(
            f'{json.dumps(m["metrics"])}', extra=self.metricType)
        controller.update_num_responses()

        self.spnfl_logger.info(f'T_RETURN_1 {m["id"]}')

    @abstractmethod
    def configure(self, server_args : dict):
        pass

    def aggregate(self, training_responses : dict[str, TrainingResponse]) -> list[ndarray]:
        fed_avg = FedAvg()
        return fed_avg.aggregate(training_responses)

    def select_clients(self, clients_states : list[ClientState]) -> list[str]:
        return AllClientsSelector().select_clients(clients_states)


    def run(self):
        # start loop
        self.mqtt_client.loop_start()
        self.logger.info('starting server...', extra=self.executionType)
        print(color.BOLD_START + 'starting server...' + color.BOLD_END)
        self.mqtt_client.publish('minifed/autoWaitContinue', json.dumps({'continue': True}))

        self.spnfl_logger.info("INIT_EXPERIMENT")

        # best accuracy so far
        best_acc = 0
        # best model so far
        best_model = None

        self.spnfl_logger.info("T_ARRIVAL_START")

        # wait trainers to connect
        while controller.get_num_trainers() < min_trainers:
            time.sleep(1)

        self.spnfl_logger.info(f'T_ARRIVAL_END {min_trainers} {controller.get_num_trainers()}')

        # begin training
        selected_qtd = 0
        round_times = []  # lista para armazenar o tempo de cada round
        while controller.get_current_round() != self.nun_rounds:
            round_start_time = time.time()  # início do round
            controller.update_current_round()
            self.logger.info(
                f'round: {controller.get_current_round()}', extra=metricType)
            print(color.RESET + '\n' + color.BOLD_START +
                  f'starting round {controller.get_current_round()}' + color.BOLD_END)

            self.spnfl_logger.info(f'START_ROUND {controller.get_current_round() - 1}')

            self.spnfl_logger.info(f'T_SELECT_START')

            # select trainers for round
            trainer_list = controller.get_trainer_list()
            if not trainer_list:
                self.logger.critical("Client's list empty", extra=executionType)
            select_trainers = self.select_clients(trainer_list)
            selected_qtd = len(select_trainers)

            self.logger.info(f"n_selected: {len(select_trainers)}", extra=metricType)
            self.logger.info(
                f"{json.dumps({'selected_trainers': select_trainers})}", extra=metricType)
            for t in trainer_list:
                if t in select_trainers:
                    # logger.info(
                    #     f'selected: {t}', extra=metricType)
                    print(
                        f'selected trainer {t} for training on round {self.current_round}')
                    m = json.dumps({'id': t, 'selected': True}).replace(' ', '')
                    self.mqtt_client.publish('minifed/selectionQueue', m)
                    self.spnfl_logger.info(f'T_SELECT {t} True')
                else:
                    # logger.info(
                    #     f'NOT_selected: {t}', extra=metricType)
                    m = json.dumps({'id': t, 'selected': False}).replace(' ', '')
                    self.mqtt_client.publish('minifed/selectionQueue', m)
                    self.spnfl_logger.info(f'T_SELECT {t} False')

            self.spnfl_logger.info(f'T_SELECT_END {selected_qtd}')

            self.spnfl_logger.info(f'T_RETURN_0_START')

            # wait for agg responses
            while controller.get_num_responses() != selected_qtd:
                time.sleep(1)
            self.spnfl_logger.info(f'T_RETURN_0_END {controller.get_num_responses()}')
            controller.reset_num_responses()  # reset num_responses for next round

            self.spnfl_logger.info(f'T_AGGREG_START')

            # aggregate and send
            agg_response = controller.agg_weights()
            response = json.dumps({'agg_response': agg_response}, default=default)

            self.spnfl_logger.info(f'T_AGGREG_END')

            self.mqtt_client.publish('minifed/posAggQueue', response)  #### T_SEND

            self.spnfl_logger.info(f'T_SEND')

            self.logger.info(f'sent aggregated weights to trainers!',
                        extra=self.executionType)
            print(f'sent aggregated weights to trainers and waiting trainers metrics!')

            self.spnfl_logger.info(f'T_RETURN_1_START')

            # wait for metrics response
            while controller.get_num_responses() != controller.get_num_trainers():
                time.sleep(1)
            self.spnfl_logger.info(f'T_RETURN_1_END {controller.get_num_responses()}')

            # spnfl_logger.info(f'T_COMPUTE_START')
            controller.reset_num_responses()  # reset num_responses for next round
            mean_acc = controller.get_mean_acc()
            self.logger.info(f'mean_accuracy: {mean_acc}\n', extra=metricType)
            print(color.GREEN +
                  f'mean accuracy on round {controller.get_current_round()} was {mean_acc}\n' + color.RESET)

            # calcular tempo do round e estimar tempo restante
            round_end_time = time.time()
            round_duration = round_end_time - round_start_time
            round_times.append(round_duration)
            rounds_done = controller.get_current_round()
            rounds_left = self.nun_rounds - rounds_done
            if rounds_done > 0 and rounds_left > 0:
                avg_time = sum(round_times) / len(round_times)
                est_remaining = avg_time * rounds_left
                mins, secs = divmod(int(est_remaining), 60)
                print(
                    color.BLUE + f"Estimated time remaining until the end of the experiment: {mins}m {secs}s" + color.RESET)

            self.spnfl_logger.info(f'T_SAVE_START')
            if mean_acc >= best_acc:
                best_model = controller.get_global_model()
                best_acc = mean_acc
            self.spnfl_logger.info(f'T_SAVE_END')

            # spnfl_logger.info(f'ROUND_DURATION {round_duration}')

            # update stop queue or continue process
            if mean_acc >= self.stop_acc:
                with open(self.saved_model_file, "w", encoding="utf-8") as f:
                    json.dump(best_model, f, ensure_ascii=False, indent=2)
                # spnfl_logger.info(f'T_SAVE_END')

                self.logger.info('stop_condition: accuracy', extra=metricType)
                print(color.RED + f'accuracy threshold met! stopping the training!')
                m = json.dumps({'stop': True})
                self.mqtt_client.publish('minifed/stopQueue', m)
                time.sleep(1)  # time for clients to finish
                # spnfl_logger.info(f'T_COMPUTE_END')
                self.spnfl_logger.info(f'END_ROUND {controller.get_current_round()}')
                exit()

            # spnfl_logger.info(f'T_SAVE_END')
            controller.reset_acc_list()
            # spnfl_logger.info(f'T_COMPUTE_END')
            self.spnfl_logger.info(f'END_ROUND {controller.get_current_round()}')

        # spnfl_logger.info(f'T_SAVE_START')
        with open(self.saved_model_file, "w", encoding="utf-8") as f:
            json.dump(best_model, f, ensure_ascii=False, indent=2)
        # spnfl_logger.info(f'T_SAVE_END')

        self.logger.info('stop_condition: rounds', extra=metricType)
        print(color.RED + f'rounds threshold met! stopping the training!' + color.RESET)
        self.mqtt_client.publish('minifed/stopQueue', m)
        self.mqtt_client.loop_stop()