import subprocess
import tempfile

from fed.fed_node import FedNode


class FedBroker(FedNode):
    def __init__(self):
        super().__init__()
        self.broker_id = ""
        self.broker_address = ""
        self.broker_folder = ""
        self.config = ""

        """ Por padrao, o mosquitto ja vem com essas configs
        self.configs = {
            "
            persistence false
            log_dest stdout
            allow_anonymous True
            connection_messages True
            listener 1883
            sys_interval 5
            "
        }
        """

    def args_to_config(self, broker_args: dict) -> str:
        lines = []
        for k, v in broker_args.items():
            if isinstance(v, bool):
                v = str(v).lower()
            lines.append(f"{k} {v}")
        return "\n".join(lines)

    def configure(self, broker_id, broker_addr, broker_folder, broker_args : dict):
        self.broker_address = broker_addr
        self.broker_folder = broker_folder
        self.broker_id = broker_id
        if broker_args and len(broker_args):
            self.configs = self.args_to_config(broker_args)


    def run(self):
        conf_path = ""
        if len(self.configs):
            with tempfile.NamedTemporaryFile("w", delete=False) as f:
                f.write(self.configs)
                conf_path = f.name

        p = subprocess.Popen(
            ["mosquitto", "-c", conf_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
