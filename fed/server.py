import logging
import time
from abc import abstractmethod

import numpy as np
from numpy import ndarray
import paho.mqtt.client as mqtt
import json

from fed.aggregators.fedavg import FedAvg
from fed.client_selectors.all_clients_selector import AllClientsSelector
from fed.client_state import ClientState
from fed.training_response import TrainingResponse


class Server:
    def __init__(self, broker_addr, experiments_result_folder, **server_args):
        self.fed_clients = []

        # connect on queue
        client_mqtt = mqtt.Client('server')
        client_mqtt.connect(broker_addr, bind_port=1883)
        client_mqtt.on_connect = self.on_connect
        client_mqtt.message_callback_add('minifed/registerQueue', self.on_message_register)
        client_mqtt.message_callback_add('minifed/preAggQueue', self.on_message_agg)
        client_mqtt.message_callback_add('minifed/metricsQueue', self.on_message_metrics)
        client_mqtt.message_callback_add('minifed/ready', self.on_message_ready)

        self.server_args = server_args
        self.broker_addr = broker_addr
        self.saved_model_file = f'{experiments_result_folder}/best.model'
        self.min_trainers = server_args["min_trainers"]
        self.nun_rounds = server_args["num_rounds"]
        self.stop_acc = server_args["stop_acc"]
        self.client_args = server_args.get("client")
        self.metricType = {"infotype": "METRIC"}
        self.executionType = {"infotype": "EXECUT"}

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

        # class for coloring messages on terminal
        class color:
            BLUE = '\033[94m'
            GREEN = '\033[92m'
            YELLOW = '\033[93m'
            RED = '\033[91m'
            BOLD_START = '\033[1m'
            BOLD_END = '\033[0m'
            RESET = "\x1B[0m"

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
        for metric in m['metrics']:
            self.fed_clients[m['id']].set_metric(metric, m['metrics'][metric])
        self.logger.info(
            f'trainer number {m["id"]} just joined the pool', extra=self.executionType)
        print(
            f'trainer number {m["id"]} just joined the pool')

        client.publish(
            'minifed/serverArgs', json.dumps({"id": m["id"], "args": self.client_args}))

    # callback for preAggQueue: get weights of trainers, aggregate and send back
    def on_message_agg(self, client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))

        self.spnfl_logger.info(f'T_RETURN_0 {m["id"]} {m["success"]}')

        if m['success']:
            client_training_response = {}
            weights = [np.asarray(w, dtype=np.float32) for w in m['weights']]
            client_training_response["weights"] = weights

            if 'training_args' in m:
                client_training_response["training_args"] = m['training_args']

            num_samples = m['num_samples']
            client_training_response["num_samples"] = num_samples
            controller.add_client_training_response(
                m['id'], client_training_response)
            controller.update_num_responses()
            logger.info(
                f'received weights from trainer {m["id"]}!', extra=executionType)
            print(f'received weights from trainer {m["id"]}!')
        else:
            print(f'client {m["id"]} failed in training!')



    # callback for metricsQueue: get the metrics from each client after it finish its round
    def on_message_metrics(self, client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))
        controller.add_accuracy(m['metrics']['accuracy'])
        controller.update_metrics(m["id"], m['metrics'])
        m["metrics"]["client_name"] = m["id"]
        logger.info(
            f'{json.dumps(m["metrics"])}', extra=metricType)
        controller.update_num_responses()

        spnfl_logger.info(f'T_RETURN_1 {m["id"]}')

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
        client.loop_start()
        logger.info('starting server...', extra=executionType)
        print(color.BOLD_START + 'starting server...' + color.BOLD_END)
        client.publish('minifed/autoWaitContinue', json.dumps({'continue': True}))

        spnfl_logger.info("INIT_EXPERIMENT")

        # best accuracy so far
        best_acc = 0
        # best model so far
        best_model = None

        spnfl_logger.info("T_ARRIVAL_START")

        # wait trainers to connect
        while controller.get_num_trainers() < min_trainers:
            time.sleep(1)

        spnfl_logger.info(f'T_ARRIVAL_END {min_trainers} {controller.get_num_trainers()}')

        # begin training
        selected_qtd = 0
        round_times = []  # lista para armazenar o tempo de cada round
        while controller.get_current_round() != nun_rounds:
            round_start_time = time.time()  # início do round
            controller.update_current_round()
            logger.info(
                f'round: {controller.get_current_round()}', extra=metricType)
            print(color.RESET + '\n' + color.BOLD_START +
                  f'starting round {controller.get_current_round()}' + color.BOLD_END)

            spnfl_logger.info(f'START_ROUND {controller.get_current_round() - 1}')

            spnfl_logger.info(f'T_SELECT_START')

            # select trainers for round
            trainer_list = controller.get_trainer_list()
            if not trainer_list:
                logger.critical("Client's list empty", extra=executionType)
            select_trainers = controller.select_trainers_for_round()
            selected_qtd = len(select_trainers)

            logger.info(f"n_selected: {len(select_trainers)}", extra=metricType)
            logger.info(
                f"{json.dumps({'selected_trainers': select_trainers})}", extra=metricType)
            for t in trainer_list:
                if t in select_trainers:
                    # logger.info(
                    #     f'selected: {t}', extra=metricType)
                    print(
                        f'selected trainer {t} for training on round {controller.get_current_round()}')
                    m = json.dumps({'id': t, 'selected': True}).replace(' ', '')
                    client.publish('minifed/selectionQueue', m)
                    spnfl_logger.info(f'T_SELECT {t} True')
                else:
                    # logger.info(
                    #     f'NOT_selected: {t}', extra=metricType)
                    m = json.dumps({'id': t, 'selected': False}).replace(' ', '')
                    client.publish('minifed/selectionQueue', m)
                    spnfl_logger.info(f'T_SELECT {t} False')

            spnfl_logger.info(f'T_SELECT_END {selected_qtd}')

            spnfl_logger.info(f'T_RETURN_0_START')

            # wait for agg responses
            while controller.get_num_responses() != selected_qtd:
                time.sleep(1)
            spnfl_logger.info(f'T_RETURN_0_END {controller.get_num_responses()}')
            controller.reset_num_responses()  # reset num_responses for next round

            spnfl_logger.info(f'T_AGGREG_START')

            # aggregate and send
            agg_response = controller.agg_weights()
            response = json.dumps({'agg_response': agg_response}, default=default)

            spnfl_logger.info(f'T_AGGREG_END')

            client.publish('minifed/posAggQueue', response)  #### T_SEND

            spnfl_logger.info(f'T_SEND')

            logger.info(f'sent aggregated weights to trainers!',
                        extra=executionType)
            print(f'sent aggregated weights to trainers and waiting trainers metrics!')

            spnfl_logger.info(f'T_RETURN_1_START')

            # wait for metrics response
            while controller.get_num_responses() != controller.get_num_trainers():
                time.sleep(1)
            spnfl_logger.info(f'T_RETURN_1_END {controller.get_num_responses()}')

            # spnfl_logger.info(f'T_COMPUTE_START')
            controller.reset_num_responses()  # reset num_responses for next round
            mean_acc = controller.get_mean_acc()
            logger.info(f'mean_accuracy: {mean_acc}\n', extra=metricType)
            print(color.GREEN +
                  f'mean accuracy on round {controller.get_current_round()} was {mean_acc}\n' + color.RESET)

            # calcular tempo do round e estimar tempo restante
            round_end_time = time.time()
            round_duration = round_end_time - round_start_time
            round_times.append(round_duration)
            rounds_done = controller.get_current_round()
            rounds_left = nun_rounds - rounds_done
            if rounds_done > 0 and rounds_left > 0:
                avg_time = sum(round_times) / len(round_times)
                est_remaining = avg_time * rounds_left
                mins, secs = divmod(int(est_remaining), 60)
                print(
                    color.BLUE + f"Estimated time remaining until the end of the experiment: {mins}m {secs}s" + color.RESET)

            spnfl_logger.info(f'T_SAVE_START')
            if mean_acc >= best_acc:
                best_model = controller.get_global_model()
                best_acc = mean_acc
            spnfl_logger.info(f'T_SAVE_END')

            # spnfl_logger.info(f'ROUND_DURATION {round_duration}')

            # update stop queue or continue process
            if mean_acc >= stop_acc:
                with open(saved_model_file, "w", encoding="utf-8") as f:
                    json.dump(best_model, f, ensure_ascii=False, indent=2)
                # spnfl_logger.info(f'T_SAVE_END')

                logger.info('stop_condition: accuracy', extra=metricType)
                print(color.RED + f'accuracy threshold met! stopping the training!')
                m = json.dumps({'stop': True})
                client.publish('minifed/stopQueue', m)
                time.sleep(1)  # time for clients to finish
                # spnfl_logger.info(f'T_COMPUTE_END')
                spnfl_logger.info(f'END_ROUND {controller.get_current_round()}')
                exit()

            # spnfl_logger.info(f'T_SAVE_END')
            controller.reset_acc_list()
            # spnfl_logger.info(f'T_COMPUTE_END')
            spnfl_logger.info(f'END_ROUND {controller.get_current_round()}')

        # spnfl_logger.info(f'T_SAVE_START')
        with open(saved_model_file, "w", encoding="utf-8") as f:
            json.dump(best_model, f, ensure_ascii=False, indent=2)
        # spnfl_logger.info(f'T_SAVE_END')

        logger.info('stop_condition: rounds', extra=metricType)
        print(color.RED + f'rounds threshold met! stopping the training!' + color.RESET)
        client.publish('minifed/stopQueue', m)
        client.loop_stop()