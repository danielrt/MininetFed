import threading
from abc import abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt


class FedTopics(Enum):
    CLIENT_REGISTER = "client_register"
    CLIENT_READY = "client_ready"
    CLIENT_WEIGHTS = "client_weights"
    CLIENT_METRICS = "client_metrics"
    CLIENT_SELECTION = "client_selection"
    CLIENT_ACCEPTED = "client_accepted"
    SERVER_WEIGHTS = "server_weights"
    STOP = "stop"


class FedNode:
    def __init__(self):
        self.mqtt_client: Optional[mqtt.Client] = None
        self.node_id: str = ""
        self.node_folder: str = ""
        self.node_args: Optional[Dict[str, Any]] = None
        self.subscribed_fed_messages: Optional[List[FedTopics]] = None

        self._connected_event = threading.Event()

    def configure(self, node_id, broker_addr, node_folder, node_args: Dict[str, Any]):
        self.node_id = node_id
        self.node_args = node_args
        self.node_folder = node_folder

        # ==== Padrão novo: paho-mqtt 2.x, MQTT v5, callback API v2 ====
        self.mqtt_client = mqtt.Client(
            client_id=node_id,
            protocol=mqtt.MQTTv5,  # se quiser manter v3.1.1, pode tirar esse argumento
        )
        # ===============================================================

        # Callbacks
        self.mqtt_client.on_connect = self.on_connect
        # (opcional) se quiser tratar desconexões:
        # self.mqtt_client.on_disconnect = self.on_disconnect

        # Registra callbacks específicos para cada tópico
        self.mqtt_client.message_callback_add(
            FedTopics.CLIENT_REGISTER.value, self.on_client_register_super
        )
        self.mqtt_client.message_callback_add(
            FedTopics.CLIENT_READY.value, self.on_client_ready_super
        )
        self.mqtt_client.message_callback_add(
            FedTopics.CLIENT_WEIGHTS.value, self.on_client_weights_super
        )
        self.mqtt_client.message_callback_add(
            FedTopics.CLIENT_METRICS.value, self.on_client_metrics_super
        )
        self.mqtt_client.message_callback_add(
            FedTopics.CLIENT_SELECTION.value, self.on_client_selection_super
        )
        self.mqtt_client.message_callback_add(
            FedTopics.CLIENT_ACCEPTED.value, self.on_client_accepted_super
        )
        self.mqtt_client.message_callback_add(
            FedTopics.SERVER_WEIGHTS.value, self.on_server_weights_super
        )
        self.mqtt_client.message_callback_add(
            FedTopics.STOP.value, self.on_stop_super
        )

        # Usa 'port', não 'bind_port'
        self.mqtt_client.connect(host=broker_addr, port=1883)

    def start_communication_loop(self):
        if self.mqtt_client is not None:
            self.mqtt_client.loop_start()

    def stop_communication_loop(self):
        if self.mqtt_client is not None:
            self.mqtt_client.loop_stop()

    def wait_until_connected(self, timeout: float | None = None) -> bool:
        """
        Bloqueia até o on_connect ser chamado e os tópicos serem assinados,
        ou até 'timeout' (em segundos). Retorna True se conectou a tempo.
        """
        return self._connected_event.wait(timeout=timeout)

    def get_node_id(self):
        return self.node_id

    def get_node_folder(self):
        return self.node_folder

    def get_node_args(self):
        return self.node_args

    def publish_to(self, fed_topic: FedTopics, payload: Optional[str]):
        if self.mqtt_client is not None:
            info = self.mqtt_client.publish(fed_topic.value, payload, qos=1)
            # log opcional
            #print(f"[{self.node_id}] publish {fed_topic.value} rc={info.rc}, mid={info.mid}")

    # ====== Callbacks ======

    # NOVO PADRÃO: com 'properties' extra
    def on_connect(self, client, userdata, flags, rc, properties=None):
        """
        Callback compatível com a API de callbacks v2 (paho-mqtt 2.x).
        Para MQTT v5, 'properties' é um objeto Properties; para v3.1.1, vem None.
        """
        topics = self.get_topics_to_subscribe()
        for topic in topics:
            if isinstance(topic, FedTopics):
                topic_str = topic.value
            else:
                topic_str = str(topic)
            self.mqtt_client.subscribe(topic_str)

        # SINALIZA que já conectou e assinou
        self._connected_event.set()

    # (Opcional) também no padrão novo
    def on_disconnect(self, client, userdata, rc, properties=None):
        print(f"[FedNode] Desconectado do broker: rc={rc}")

    def get_topics_to_subscribe(self) -> List[FedTopics]:
        """
        Subclasses devem sobrescrever este metodo para retornar
        a lista de tópicos FedTopics a serem assinados.
        """
        return []

    def on_client_register_super(self, client, userdata, message):
        self.on_client_register(message)

    def on_client_register(self, message):
        pass

    def on_client_ready_super(self, client, userdata, message):
        self.on_client_ready(message)

    def on_client_ready(self, message):
        pass

    def on_client_weights_super(self, client, userdata, message):
        self.on_client_weights(message)

    def on_client_weights(self, message):
        pass

    def on_client_metrics_super(self, client, userdata, message):
        self.on_client_metrics(message)

    def on_client_metrics(self, message):
        pass

    def on_client_selection_super(self, client, userdata, message):
        self.on_client_selection(message)

    def on_client_selection(self, message):
        pass

    def on_client_accepted_super(self, client, userdata, message):
        self.on_client_accepted(message)

    def on_client_accepted(self, message):
        pass

    def on_server_weights_super(self, client, userdata, message):
        self.on_server_weights(message)

    def on_server_weights(self, message):
        pass

    def on_stop_super(self, client, userdata, message):
        self.on_stop()

    def on_stop(self):
        pass

    @abstractmethod
    def run(self):
        pass
