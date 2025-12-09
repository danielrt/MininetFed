import os
import subprocess

from mininetfed.core.nodes.fed_node import FedNode


class FedBroker(FedNode):
    def __init__(self):
        super().__init__()
        self.broker_id = ""
        self.broker_address = ""
        self.broker_folder = ""
        self.config_file = ""

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

        default_configs = f"""\
persistence false
log_dest stdout
log_dest file {self.broker_folder}/mosquitto.log
allow_anonymous true
connection_messages true
listener 1883 0.0.0.0
sys_interval 5
"""
        configs = ""
        if broker_args and len(broker_args):
            configs = self.args_to_config(broker_args)
        else:
            configs = default_configs

        self.config_file = os.path.join(self.broker_folder, "mosquitto.conf")
        with open(self.config_file, "w", encoding="utf-8") as config_f:
            config_f.write(configs)

        with open(f"{self.broker_folder}/mosquitto.log", "w", encoding="utf-8") as config_f:
            config_f.write("")

    def run(self):

        cmd = ["mosquitto", "-c", self.config_file]
        print(f"[FedBroker] Iniciando mosquitto com comando: {' '.join(cmd)}")
        print(f"[FedBroker] Usando config: {self.config_file}")

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[FedBroker] mosquitto saiu com erro: {e.returncode}")

