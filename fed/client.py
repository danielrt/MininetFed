import json
import logging
import sys
import time
from abc import abstractmethod

from numpy import ndarray
from paho import mqtt
from scipy.cluster.hierarchy import weighted

from fed.client_info import ClientInfo
from fed.metrics import Metrics
from fed.training_data import TrainingData
from fed.dataset_info import DatasetInfo


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
        self.client_id : str = ""
        self.client_folder : str = ""
        self.logger = None
        self.spnfl_logger = None
        self.mqtt_client = None
        self.stop = False
        self.dataset_info : DatasetInfo | None = None
        self.client_info : ClientInfo | None = None

    @abstractmethod
    def configure(self, client_args: dict):
        pass

    """ Retorna o numero de samples do dataset"""
    @abstractmethod
    def prepare_data(self, path_to_data : str) -> DatasetInfo:
        pass
    
    @abstractmethod
    def set_client_info(self, client_info : ClientInfo):
        pass

    @abstractmethod
    def update_weights(self, global_weights : list[ndarray]):
        pass

    @abstractmethod
    def get_weights(self) -> list[ndarray]:
        pass

    @abstractmethod
    def fit(self) -> bool:
        pass

    @abstractmethod
    def evaluate(self) -> Metrics:
        pass

    def configure_default(self, broker_addr, client_id, client_folder):
        client = mqtt.Client(self.client_id)
        client.connect(broker_addr, keepalive=0)
        client.on_connect = self.on_connect
        client.message_callback_add('minifed/selectionQueue', self.on_message_selection)
        client.message_callback_add('minifed/posAggQueue', self.on_message_agg)
        client.message_callback_add('minifed/stopQueue', self.on_message_stop)
        client.message_callback_add('minifed/accept', self.on_message_accept)

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

        self.dataset_info = self.prepare_data(self.client_folder)
        self.client_info = ClientInfo(self.client_id)
        self.set_client_info(self.client_info)

    # subscribe to queues on connection
    def on_connect(self, client, userdata, flags, rc):
        subscribe_queues = ['minifed/selectionQueue',
                            'minifed/posAggQueue', 'minifed/stopQueue', 'minifed/accept']
        for s in subscribe_queues:
            self.mqtt_client.subscribe(s)

    def on_message_accept(self, client, userdata, message):
        msg = json.loads(message.payload.decode("utf-8"))
        if msg['client_id'] == self.client_id:
            if msg['accept']:
                client.publish('minifed/ready',
                               json.dumps(self.dataset_info.to_json()))
                self.logger.info(f'client {self.client_id} was accepted by server to join')
            else:
                self.logger.info(f'client {self.client_id} was denied by server to join')
                self.stop = True
    """
    callback for selectionQueue: the selection queue is sent by the server; 
    the client checks if it's selected for the current round or not. If yes, 
    the client trains and send the training results back.
    """
    def on_message_selection(self, client, userdata, message):
        msg = json.loads(message.payload.decode("utf-8"))
        client_id = msg['id']
        selected = bool(msg['selected'])
        round_id = int(msg['round_id'])
        if client_id == self.client_id:
            self.spnfl_logger.info(f'START_ROUND {round_id}')
            if selected:
                self.spnfl_logger.info(f'T_SELECT True')
                print(Color.BOLD_START + '[{}] new round starting'.format(round_id) + Color.BOLD_END)
                print(
                    f'client was selected for training this round and will start training!')

                t0 = time.time()
                was_success = self.fit()
                t_train = time.time() - t0
                weights = None
                if was_success:
                    weights = self.get_weights()
                client_training_data = TrainingData(self.client_id, was_success, round_id, weights)

                self.spnfl_logger.info(f"T_TRAIN {was_success} {t_train}")
                response = json.dumps(client_training_data.to_json())

                client.publish('minifed/preAggQueue', response)
                self.spnfl_logger.info(f'T_RETURN_0')
                print(f'finished training and sent weights!')
            else:
                self.spnfl_logger.info(f'T_SELECT False')
                print(Color.BOLD_START + '[{}] new round starting'.format(round_id) + Color.BOLD_END)
                print(f'trainer WAS NOT selected for training this round')

    # callback for posAggQueue: gets aggregated weights and publish validation results on the metricsQueue
    def on_message_agg(self, client, userdata, message):
        global selected
        self.spnfl_logger.info(f'T_SEND')
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

        self.mqtt_client.publish('minifed/registerQueue', self.dataset_info.to_json())
        self.spnfl_logger.info(f'T_ARRIVAL')
        print(Color.BOLD_START +
              f'trainer {self.client_id} connected!\n' + Color.BOLD_END)

        while not self.stop:
            time.sleep(1)

        self.mqtt_client.loop_stop()
        exit()