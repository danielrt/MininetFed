import json
import logging
import sys
import time
from abc import abstractmethod

from numpy import ndarray

from mininetfed.core.dto.client_info import ClientInfo
from mininetfed.core.nodes.fed_node import FedNode, FedTopics
from mininetfed.core.dto.metrics import Metrics
from mininetfed.core.dto.training_data import TrainingData
from mininetfed.core.dto.dataset_info import DatasetInfo
from mininetfed.core.utils import Color


class FedClient(FedNode):
    def __init__(self):
        super().__init__()
        self.client_id : str = ""
        self.current_round = 0
        self.logger = None
        self.spnfl_logger = None
        self.stop = False
        self.dataset_info : DatasetInfo | None = None
        self.client_info : ClientInfo | None = None

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

    def get_client_id(self) -> str:
        return self.client_id

    def get_topics_to_subscribe(self) -> list[FedTopics]:
        return [FedTopics.CLIENT_SELECTION, FedTopics.CLIENT_ACCEPTED,
                  FedTopics.SERVER_WEIGHTS, FedTopics.STOP]

    def configure(self, client_id, broker_addr, client_folder, client_args):
        super().configure(client_id, broker_addr, client_folder, client_args)

        self.client_id = client_id

        # logger geral
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
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

        self.dataset_info = self.prepare_data(client_folder)
        self.client_info = ClientInfo(client_id)
        self.set_client_info(self.client_info)

    def on_client_accepted(self, message):
        m = message.payload.decode("utf-8")
        msg = json.loads(m)
        if msg['client_id'] == self.client_id:
            if msg['accepted']:
                super().publish_to(FedTopics.CLIENT_READY,
                               self.dataset_info.to_json())
                self.logger.info(f'client {self.client_id} was accepted by server to join')
                print(f'client {self.client_id} was accepted by server to join')
            else:
                self.logger.info(f'client {self.client_id} was denied by server to join')
                print(f'client {self.client_id} was denied by server to join')
                self.stop = True
    """
    callback for selectionQueue: the selection queue is sent by the server; 
    the client checks if it's selected for the current round or not. If yes, 
    the client trains and send the training results back.
    """
    def on_client_selection(self, message):
        msg = json.loads(message.payload.decode("utf-8"))
        client_id = msg['id']
        selected = bool(msg['selected'])
        self.current_round = int(msg['round_id'])
        if client_id == self.client_id:
            self.spnfl_logger.info(f'START_ROUND {self.current_round}')
            if selected:
                self.spnfl_logger.info(f'T_SELECT True')
                print(Color.BOLD_START + '[{}] new round starting'.format(self.current_round) + Color.BOLD_END)
                self.logger.info(f"[{self.current_round}] new round starting")
                print(
                    f'client was selected for training this round and will start training!')
                self.logger.info(f'client was selected for training this round and will start training!')

                t0 = time.time()
                was_success = self.fit()
                t_train = time.time() - t0
                weights = None
                if was_success:
                    weights = self.get_weights()
                client_training_data = TrainingData(self.client_id, was_success, self.current_round, weights)

                self.spnfl_logger.info(f"T_TRAIN {was_success} {t_train}")

                super().publish_to(FedTopics.CLIENT_WEIGHTS, client_training_data.to_json())
                self.spnfl_logger.info(f'T_RETURN_0')
                print(f'finished training and sent weights!')
                self.logger.info(f'finished training and sent weights!')
            else:
                self.spnfl_logger.info(f'T_SELECT False')
                print(Color.BOLD_START + '[{}] new round starting'.format(self.current_round) + Color.BOLD_END)
                self.logger.info(f"[{self.current_round}] new round starting")
                print(f'trainer WAS NOT selected for training this round')
                self.logger.info(f'trainer WAS NOT selected for training this round')

    # callback for posAggQueue: gets aggregated weights and publish validation results on the metricsQueue
    def on_server_weights(self, message):
        self.spnfl_logger.info(f'T_SEND')
        print(f'received aggregated weights!')
        self.logger.info(f'received aggregated weights!')
        agg_training_data = TrainingData.from_json(message.payload.decode("utf-8"))

        self.update_weights(agg_training_data.get_weights())

        metrics = self.evaluate()
        print(f'sending eval metrics!\n')
        self.logger.info(f'sending eval metrics!')
        super().publish_to(FedTopics.CLIENT_METRICS, metrics.to_json())

        self.spnfl_logger.info(f'T_RETURN_1')
        self.spnfl_logger.info(f'END_ROUND {self.current_round}')

    # callback for stopQueue: if conditions are met, stop training and exit process
    def on_stop(self):
        print(Color.RED + f'received message to stop!')
        self.logger.info(f'received message to stop!')
        self.stop = True

    def run(self):
        # start waiting for jobs
        super().start_communication_loop()

        # Espera até estar conectado + tópicos assinados
        # (5 segundos de timeout, por exemplo)
        if not super().wait_until_connected(timeout=5.0):
            print(f"[CLIENT {self.client_id}] Failed to connect/subscribe to broker")
            self.logger.info(f"[CLIENT {self.client_id}] Failed to connect/subscribe to broker")
            return

        self.spnfl_logger.info("INIT_EXPERIMENT")

        super().publish_to(FedTopics.CLIENT_REGISTER, self.client_info.to_json())
        self.spnfl_logger.info(f'T_ARRIVAL')
        print(Color.BOLD_START +
              f'trainer {self.client_id} connected!\n' + Color.BOLD_END)
        self.logger.info(f'trainer {self.client_id} connected!\n')

        while not self.stop:
            time.sleep(1)

        super().stop_communication_loop()