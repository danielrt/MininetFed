from abc import abstractmethod
from enum import Enum

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
        self.mqtt_client = None
        self.node_id : str = ""
        self.node_folder : str = ""
        self.node_args : dict | None = None
        self.subscribed_fed_messages : list[FedTopics] | None = None

    def configure(self, node_id, broker_addr, node_folder, node_args : dict):
        self.node_id = node_id
        self.node_args = node_args
        self.node_folder = node_folder
        self.mqtt_client = mqtt.Client(node_id)
        self.mqtt_client.connect(broker_addr, bind_port=1883)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.message_callback_add(FedTopics.CLIENT_REGISTER.value, self.on_client_register_super)
        self.mqtt_client.message_callback_add(FedTopics.CLIENT_READY.value, self.on_client_ready_super)
        self.mqtt_client.message_callback_add(FedTopics.CLIENT_WEIGHTS.value, self.on_client_weights_super)
        self.mqtt_client.message_callback_add(FedTopics.CLIENT_METRICS.value, self.on_client_metrics_super)
        self.mqtt_client.message_callback_add(FedTopics.CLIENT_SELECTION.value, self.on_client_selection_super)
        self.mqtt_client.message_callback_add(FedTopics.CLIENT_ACCEPTED.value, self.on_client_accepted_super)
        self.mqtt_client.message_callback_add(FedTopics.SERVER_WEIGHTS.value, self.on_server_weights_super)
        self.mqtt_client.message_callback_add(FedTopics.STOP.value, self.on_stop)

    def start_communication_loop(self):
        self.mqtt_client.loop_start()

    def stop_communication_loop(self):
        self.mqtt_client.loop_stop()

    def get_node_id(self):
        return self.node_id

    def get_node_folder(self):
        return self.node_folder

    def get_node_args(self):
        return self.node_args

    def publish_to(self, fed_topic : FedTopics, payload : str | None):
        self.mqtt_client.publish(fed_topic.value, payload)

    def on_connect(self, client, userdata, flags, rc):
        topics = self.get_topics_to_subscribe()
        for topic in topics:
            self.mqtt_client.subscribe(topic)

    def get_topics_to_subscribe(self) -> list[FedTopics]:
        pass

    def on_client_register_super(self, client, userdata, message):
        self.on_client_register(message)

    def on_client_register(self,message):
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