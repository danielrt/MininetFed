import json
import logging
import sys
import time
from abc import abstractmethod

from numpy import ndarray
from paho import mqtt

from fed.client_metrics import ClientMetrics


class Color:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD_START = '\033[1m'
    BOLD_END = '\033[0m'
    RESET = "\x1B[0m"

class Client:
    def __init__(self):
        self.client_id = ""
        self.client_folder = ""
        self.logger = None
        self.spnfl_logger = None
        self.mqtt_client = None
        self.stop = False

    @abstractmethod
    def configure(self, client_args: dict):
        pass

    @abstractmethod
    def prepare_data(self, path_to_data : str):
        pass

    @abstractmethod
    def update(self, global_weights : list[ndarray]):
        pass

    @abstractmethod
    def fit(self) -> list[ndarray]:
        pass

    @abstractmethod
    def evaluate(self) -> ClientMetrics:
        pass

    def configure_default(self, broker_addr, client_id, client_folder):
        client = mqtt.Client(self.client_id)
        client.connect(broker_addr, keepalive=0)
        client.on_connect = self.on_connect
        client.message_callback_add('minifed/selectionQueue', self.on_message_selection)
        client.message_callback_add('minifed/posAggQueue', self.on_message_agg)
        client.message_callback_add('minifed/stopQueue', self.on_message_stop)

        self.client_id = client_id
        self.client_folder = client_folder

        # logger geral
        log_format = "%(asctime)s - %(infotype)-6s - %(levelname)s - %(message)s"
        self.logger = logging.getLogger("client")
        self.logger.setLevel(logging.INFO)
        log_file = f'{client_folder}/{client_id}.log'
        h_general = logging.FileHandler(filename=log_file, mode="w")
        h_general.setFormatter(logging.Formatter(log_format))
        self.logger.addHandler(h_general)
        print(f"log_file: {log_file}", file=sys.stderr)

        # logger spnfl (artigo https://sol.sbc.org.br/index.php/sbrc/article/view/35122/34913)
        format_spnfl = "%(asctime)s - %(message)s"
        self.spnfl_logger = logging.getLogger("spnfl")
        self.spnfl_logger.setLevel(logging.INFO)
        self.spnfl_logger.propagate = False
        spnfl_log_file = f'{client_folder}/{client_id}_spn.log'
        h_spnfl = logging.FileHandler(spnfl_log_file, mode="w")
        h_spnfl.setFormatter(logging.Formatter(format_spnfl))
        self.spnfl_logger.addHandler(h_spnfl)

        self.split_data(self.client_folder)

    # subscribe to queues on connection
    def on_connect(self, client, userdata, flags, rc):
        subscribe_queues = ['minifed/selectionQueue',
                            'minifed/posAggQueue', 'minifed/stopQueue']
        for s in subscribe_queues:
            self.mqtt_client.subscribe(s)

    """
    callback for selectionQueue: the selection queue is sent by the server; 
    the client checks if it's selected for the current round or not. If yes, 
    the client trains and send the training results back.
    """
    def on_message_selection(self, client, userdata, message):
        global selected
        global n_round
        msg = json.loads(message.payload.decode("utf-8"))
        client_id = msg['id']
        selected = bool(msg['selected'])
        round_id = int(msg['round_id'])
        if client_id == self.client_id:
            self.spnfl_logger.info(f'START_ROUND {round_id}')
            if selected:
                self.spnfl_logger.info(f'T_SELECT True')
                selected = True
                print(Color.BOLD_START + '[{}] new round starting'.format(round_id) + Color.BOLD_END)
                print(
                    f'client was selected for training this round and will start training!')

                resp_dict = {'id': CLIENT_NAME, 'success': True}
                t0 = time.time()
                try:
                    weights = self.fit()
                    resp_dict['weights'] = trainer.get_weights()
                    resp_dict['num_samples'] = trainer.get_num_samples()
                    if has_method(trainer, 'get_training_args'):
                        resp_dict['training_args'] = trainer.get_training_args()
                except Exception:
                    print(traceback.format_exc())
                    resp_dict['success'] = False
                t_train = time.time() - t0

                spnfl_logger.info(f"T_TRAIN {resp_dict['success']} {t_train}")
                response = json.dumps(resp_dict, default=default)

                client.publish('minifed/preAggQueue', response)
                spnfl_logger.info(f'T_RETURN_0')
                print(f'finished training and sent weights!')
            else:
                spnfl_logger.info(f'T_SELECT False')
                selected = False
                print(color.BOLD_START + '[{}] new round starting'.format(n_round[client_id]) + color.BOLD_END)
                print(f'trainer was not selected for training this round')

    # callback for posAggQueue: gets aggregated weights and publish validation results on the metricsQueue
    def on_message_agg(self, client, userdata, message):
        global selected
        spnfl_logger.info(f'T_SEND')
        print(f'received aggregated weights!')
        msg = json.loads(message.payload.decode("utf-8"))
        agg_weights = [np.asarray(w, dtype=np.float32)
                       for w in msg["agg_response"][CLIENT_NAME]["weights"]]
        results = trainer.all_metrics()
        results['selected'] = selected
        response = json.dumps(
            {'id': CLIENT_NAME, "metrics": results}, default=default)
        trainer.update_weights(agg_weights)

        if has_method(trainer, "agg_response_extra_info"):
            trainer.agg_response_extra_info(
                msg["agg_response"][CLIENT_NAME] | msg["agg_response"]['all'])

        print(f'sending eval metrics!\n')
        client.publish('minifed/metricsQueue', response)
        spnfl_logger.info(f'T_RETURN_1')
        spnfl_logger.info(f'END_ROUND {n_round[CLIENT_NAME] - 1}')
    # callback for stopQueue: if conditions are met, stop training and exit process
    def on_message_stop(self, client, userdata, message):
        print(Color.RED + f'received message to stop!')
        self.stop = True

    def run(self):
        # start waiting for jobs
        self.mqtt_client.loop_start()

        self.spnfl_logger.info("INIT_EXPERIMENT")

        client_metrics = self.evaluate()

        self.mqtt_client.publish('minifed/registerQueue', client_metrics.to_json())
        self.spnfl_logger.info(f'T_ARRIVAL')
        print(Color.BOLD_START +
              f'trainer {self.client_id} connected!\n' + Color.BOLD_END)

        while not self.stop:
            time.sleep(1)

        self.mqtt_client.loop_stop()
        exit()