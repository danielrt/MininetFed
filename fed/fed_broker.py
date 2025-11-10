import subprocess
import tempfile

from fed.fed_node import FedNode


class FedBroker(FedNode):
    def __init__(self):
        super().__init__()
        self.broker_id = ""
        self.broker_address = ""
        self.config = ""

    def configure(self, broker_id, broker_addr, broker_folder, broker_args : dict):
        self.broker_address = broker_addr
        self.broker_id = broker_id
        if broker_args["external"]:
            self.config = """
                persistence false
                log_dest stdout
                allow_anonymous true
                connection_messages true
                listener 10.0.0.1:1883
                sys_interval 5
            """
        else:
            self.config = """
                persistence false
                log_dest stdout
                allow_anonymous true
                connection_messages true
                listener 1883
                sys_interval 5
            """

    def run(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(self.config)
            conf_path = f.name

        p = subprocess.Popen(
            ["mosquitto", "-c", conf_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
