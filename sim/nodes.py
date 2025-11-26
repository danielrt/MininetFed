import json
import os
from pathlib import Path

from containernet.node import Docker
from containernet.term import makeTerm
from docker.errors import ImageNotFound

from sim.docker_image_builder import docker_image_exists, build_fed_broker_docker_image, build_fed_node_docker_image


class DockerFedNode(Docker):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, node_id : str, node_folder : str, dimage : str, node_args : dict | None = None):
        args = node_args or {}

        # Evita colisão de parâmetros (ex.: se alguém passou 'volumes' dentro de self.args)
        safe_args = dict(args)
        safe_args.pop("volumes", None)
        safe_args.pop("name", None)
        safe_args.pop("dimage", None)

        volumes = [f"{node_folder}:/flw:rw"]

        if not dimage:
            raise ImageNotFound(f"No Image Docker was provided.")

        if not docker_image_exists(dimage):
            raise ImageNotFound(f"Image Docker {dimage} was not found.")

        Docker.__init__(self, name=node_id, dimage=dimage, volumes=volumes, **safe_args)

    def run(self, broker_addr):
        pass

class FedClientNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, client_id : str, script: str, client_folder : str, dimage : str | None = None, client_args : dict | None = None):
        super().__init__( node_id = client_id, node_folder = client_folder, dimage = dimage, node_args = client_args)
        self.script = script
        self.client_id = client_id
        self.client_args = client_args or {}
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.client_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.client_args)}  2> err.txt """
        self.cmd("route add default gw %s" % broker_addr)
        makeTerm(self, cmd=cmd)

class FedServerNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, server_id : str, script: str | None = None, server_folder : str | None = None , dimage : str | None = None, server_args : dict | None = None):
        self.server_id = server_id
        # quando script não for passado como parametro, tem que executar o no server implementacao padrao
        self.script = script or "mininetfed_default_server.py"
        self.server_folder = server_folder or Path.cwd() / "server_output"
        if not server_folder or len(server_folder):
            self.server_folder.mkdir(exist_ok=True)
        self.server_args = server_args or {}
        super().__init__( node_id = server_id, node_folder = server_folder, dimage = dimage, node_args = server_args)
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.server_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.args)}  2> err.txt """
        self.cmd("route add default gw %s" % broker_addr)
        os.umask(0o000)
        makeTerm(self, cmd=cmd)

class FedBrokerNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed broker."""
    def __init__(self, broker_id : str, broker_folder : str | None = None , dimage : str | None = None, broker_args : dict | None = None):
        self.broker_id = broker_id
        self.script = "mininetfed_default_broker.py"
        self.broker_folder = broker_folder or Path.cwd() / "broker_output"
        if not broker_folder or len(broker_folder):
            self.broker_folder.mkdir(exist_ok=True)
        self.broker_args = broker_args or {}
        super().__init__( node_id = broker_id, node_folder = broker_folder, dimage = dimage, node_args = broker_args)
        self.cmd("iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")

    def run(self, broker_addr):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.broker_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.broker_args)}  2> err.txt """
        makeTerm(self, cmd=cmd)
