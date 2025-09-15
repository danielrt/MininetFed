from logging import Formatter

import paho.mqtt.client as mqtt
from controller import Controller
import json
import time
import numpy as np
import sys
import logging
import os

def default(obj):
    if type(obj).__module__ == np.__name__:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj.item()
    else:
        try:
            from Pyfhel import PyCtxt
            if isinstance(obj, PyCtxt):
                return obj.to_bytes().decode('cp437')
        except:
            pass
    raise TypeError('Tipo não pode ser serializado:', type(obj))


def server():
    # total args
    os.umask(0o000)
    n = len(sys.argv)

    # check args
    if n < 4:
        logging.critical("incorrect use of server.py arguments")
        # <min_clients> <num_rounds> <accuracy_threshold>
        print("correct use: python server.py <broker_address> <arquivo.log> <args>.")
        exit()

    server_args = json.loads(sys.argv[3])
    broker_addr = sys.argv[1]
    log_file = sys.argv[2] + ".log"
    saved_model_file = sys.argv[2] + "_best.model"
    spnfl_log_file = sys.argv[2] + "_spnfl.log"
    min_trainers = server_args["min_trainers"]
    client_selector = server_args["client_selector"]
    aggregator = server_args["aggregator"]
    nun_rounds = server_args["num_rounds"]
    stop_acc = server_args["stop_acc"]
    client_args = server_args.get("client")
    metricType = {"infotype": "METRIC"}
    executionType = {"infotype": "EXECUT"}

    FORMAT = "%(asctime)s - %(infotype)-6s - %(levelname)s - %(message)s"
    #logging.basicConfig(level=logging.INFO, filename=log_file,
    #                    format=FORMAT, filemode="w")
    #logger = logging.getLogger(__name__)

    # logger geral
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    h_general = logging.FileHandler(filename=log_file, mode="w")
    h_general.setFormatter(Formatter(FORMAT))
    logger.addHandler(h_general)

    # logger spnfl (artigo https://sol.sbc.org.br/index.php/sbrc/article/view/35122/34913)
    FORMAT_SPNFL = "%(asctime)s - %(message)s"
    spnfl_logger = logging.getLogger("spnfl")
    spnfl_logger.setLevel(logging.INFO)
    spnfl_logger.propagate = False  # não manda para os handlers do "myapp"
    h_spnfl = logging.FileHandler(spnfl_log_file, mode="w")
    h_spnfl.setFormatter(Formatter(FORMAT_SPNFL))
    spnfl_logger.addHandler(h_spnfl)

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
    def on_connect(client, userdata, flags, rc):
        subscribe_queues = ['minifed/registerQueue', 'minifed/preAggQueue',
                            'minifed/metricsQueue', 'minifed/ready']
        for s in subscribe_queues:
            client.subscribe(s)

    # callback for registerQueue: add trainer to the pool of trainers
    def on_message_ready(client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))
        controller.add_trainer(m["id"])

        spnfl_logger.info(f'T_ARRIVAL {m["id"]}')

    def on_message_register(client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))
        controller.update_metrics(m["id"], m['metrics'])
        logger.info(
            f'trainer number {m["id"]} just joined the pool', extra=executionType)
        print(
            f'trainer number {m["id"]} just joined the pool')

        client.publish(
            'minifed/serverArgs', json.dumps({"id": m["id"], "args": client_args}))

    # callback for preAggQueue: get weights of trainers, aggregate and send back
    def on_message_agg(client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))

        spnfl_logger.info(f'T_RETURN_0 {m["id"]} {m["success"]}')
        spnfl_logger.info(f'T_TRAIN  {m["t_train"]}')


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
    def on_message_metrics(client, userdata, message):
        m = json.loads(message.payload.decode("utf-8"))
        controller.add_accuracy(m['metrics']['accuracy'])
        controller.update_metrics(m["id"], m['metrics'])
        m["metrics"]["client_name"] = m["id"]
        logger.info(
            f'{json.dumps(m["metrics"])}', extra=metricType)
        controller.update_num_responses()

        spnfl_logger.info(f'T_RETURN_1 {m["id"]}')

    # connect on queue
    controller = Controller(min_trainers=min_trainers, num_rounds=nun_rounds,
                            client_selector=client_selector, aggregator=aggregator)
    client = mqtt.Client('server')
    client.connect(broker_addr, bind_port=1883)
    client.on_connect = on_connect
    client.message_callback_add('minifed/registerQueue', on_message_register)
    client.message_callback_add('minifed/preAggQueue', on_message_agg)
    client.message_callback_add('minifed/metricsQueue', on_message_metrics)
    client.message_callback_add('minifed/ready', on_message_ready)

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

        spnfl_logger.info(f'ROUND {controller.get_current_round()}')

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


        client.publish('minifed/posAggQueue', response) #### T_SEND

        spnfl_logger.info(f'T_SEND')

        logger.info(f'sent aggregated weights to trainers!',
                    extra=executionType)
        print(f'sent aggregated weights to trainers and waiting trainers metrics!')

        spnfl_logger.info(f'T_RETURN_1_START')

        # wait for metrics response
        while controller.get_num_responses() != controller.get_num_trainers():
            time.sleep(1)
        spnfl_logger.info(f'T_RETURN_1_END {controller.get_num_responses()}')

        spnfl_logger.info(f'T_COMPUTE_START')
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

        # update stop queue or continue process
        if mean_acc >= stop_acc:
            with open(saved_model_file, "w", encoding="utf-8") as f:
                json.dump(best_model, f, ensure_ascii=False, indent=2)
            spnfl_logger.info(f'T_SAVE_END')

            logger.info('stop_condition: accuracy', extra=metricType)
            print(color.RED + f'accuracy threshold met! stopping the training!')
            m = json.dumps({'stop': True})
            client.publish('minifed/stopQueue', m)
            time.sleep(1)  # time for clients to finish
            spnfl_logger.info(f'T_COMPUTE_END')
            exit()

        spnfl_logger.info(f'T_SAVE_END')
        controller.reset_acc_list()
        spnfl_logger.info(f'T_COMPUTE_END')

    spnfl_logger.info(f'T_SAVE_START')
    with open(saved_model_file, "w", encoding="utf-8") as f:
        json.dump(best_model, f, ensure_ascii=False, indent=2)
    spnfl_logger.info(f'T_SAVE_END')

    logger.info('stop_condition: rounds', extra=metricType)
    print(color.RED + f'rounds threshold met! stopping the training!' + color.RESET)
    client.publish('minifed/stopQueue', m)
    client.loop_stop()



if __name__ == "__main__":
    server()
