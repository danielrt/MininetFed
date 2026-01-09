import json
import os
import shlex
from pathlib import Path

from containernet.node import Docker
from containernet.term import makeTerm
from docker.errors import ImageNotFound

from mininetfed.sim.util.docker_utils import docker_image_exists, build_fed_broker_docker_image, \
    build_fed_node_docker_image, MININETFED_IMAGE_INSTALL_LOCATION

DOCKER_NODE_FOLDER = "/flw"

class DockerFedNode(Docker):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, name : str, node_folder : str, dimage : str, **kwargs):

        abs_folder_path = os.path.abspath(node_folder)
        volumes = [f"{abs_folder_path}:{DOCKER_NODE_FOLDER}:rw"]

        if not dimage:
            raise ImageNotFound(f"No Image Docker was provided.")

        if not docker_image_exists(dimage):
            raise ImageNotFound(f"Image Docker {dimage} was not found.")

        Docker.__init__(self, name=name, dimage=dimage, volumes=volumes, **kwargs)

    def run(self, broker_addr) -> Path:
        pass

class FedClientNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, name : str, script: str, client_folder : str, dimage : str | None = None, client_args : dict | None = None, **kwargs):
        self.client_id = name
        self.client_folder = os.path.abspath(client_folder)
        if len(script):
            self.script = DOCKER_NODE_FOLDER + "/" + script
        else:
            raise FileNotFoundError(f"No execution script was provided for client {self.client_id}")
        self.client_args = client_args or {}

        super().__init__(name=name, node_folder=self.client_folder, dimage=dimage, **kwargs)
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        self.cmd("route add default gw %s" % broker_addr)

        # JSON dos args, protegido para shell
        args_json = shlex.quote(json.dumps(self.client_args))

        done_file = f"{DOCKER_NODE_FOLDER}/.done"

        # Comando “interno” (sem bash -c ainda)
        inner_cmd = (
            "umask 000; "
            f"mininetfed-node-executor "
            f"--file {shlex.quote(self.script)} "
            f"--node_id {shlex.quote(self.client_id)} "
            f"--broker_addr {shlex.quote(broker_addr)} "
            f"--node_folder {DOCKER_NODE_FOLDER} "
            f"--node_args-json {args_json} "
            f"2> {DOCKER_NODE_FOLDER}/err.txt; "
            f"echo DONE > {shlex.quote(done_file)}; "
            "exec bash"
        )

        # Agora embrulha tudo em um bash -lc '<inner_cmd>'
        cmd = f"bash -lc {shlex.quote(inner_cmd)}"

        print(f"[FedServerNode] Abrindo terminal com: {cmd}")
        makeTerm(self, cmd=cmd)

        return Path(f"{self.client_folder}/.done")

class FedServerNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, name : str, script: str | None = None, server_folder : str | None = None, dimage : str | None = None, server_args : dict | None = None, **kwargs):
        self.server_id = name
        # quando script não for passado como parametro, tem que executar o no server implementacao padrao
        if script and len(script):
            self.script = DOCKER_NODE_FOLDER + "/" + script
        else:
            self.script = MININETFED_IMAGE_INSTALL_LOCATION + "/core/nodes/default_fed_server.py"

        self.server_folder = Path(server_folder) if server_folder else (Path.cwd() / "server_output")
        self.server_folder.mkdir(parents=True, exist_ok=True)

        self.server_args = server_args or {}

        server_docker_image = dimage
        if not server_docker_image:
            server_docker_image = build_fed_node_docker_image("server")["tag"]

        super().__init__(name= name, node_folder = self.server_folder, dimage = server_docker_image, **kwargs)
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        self.cmd("route add default gw %s" % broker_addr)

        # JSON dos args, protegido para shell
        args_json = shlex.quote(json.dumps(self.server_args))

        done_file = f"{DOCKER_NODE_FOLDER}/.done"

        # Comando “interno” (sem bash -c ainda)
        inner_cmd = (
            "umask 000; "
            f"mininetfed-node-executor "
            f"--file {shlex.quote(self.script)} "
            f"--node_id {shlex.quote(self.server_id)} "
            f"--broker_addr {shlex.quote(broker_addr)} "
            f"--node_folder {DOCKER_NODE_FOLDER} "
            f"--node_args-json {args_json} "
            f"2> {DOCKER_NODE_FOLDER}/err.txt; "
            f"echo DONE > {shlex.quote(done_file)}; "
            "exec bash"
        )

        # Agora embrulha tudo em um bash -lc '<inner_cmd>'
        cmd = f"bash -lc {shlex.quote(inner_cmd)}"

        print(f"[FedServerNode] Abrindo terminal com: {cmd}")
        makeTerm(self, cmd=cmd)

        return Path(f"{self.server_folder}/.done")

class FedBrokerNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed broker."""
    def __init__(self, name : str, broker_folder : str | None = None, dimage : str | None = None, broker_args : dict | None = None, **kwargs):
        self.broker_id = name
        self.script = MININETFED_IMAGE_INSTALL_LOCATION + "/core/nodes/default_fed_broker.py"
        self.broker_folder = broker_folder or Path.cwd() / "broker_output"
        if not broker_folder or len(broker_folder):
            self.broker_folder.mkdir(exist_ok=True)
        self.broker_args = broker_args or {}

        broker_docker_image = dimage
        if not broker_docker_image:
            broker_docker_image = build_fed_broker_docker_image()["tag"]

        super().__init__(name= name, node_folder = self.broker_folder, dimage = broker_docker_image, **kwargs)
        self.cmd("iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")

    def run(self, broker_addr = ""):
        broker_addr = self.IP(intf=f"{self.broker_id}-eth0")

        # JSON dos args, protegido para shell
        args_json = shlex.quote(json.dumps(self.broker_args))

        # Comando “interno” (sem bash -c ainda)
        inner_cmd = (
            "umask 000; "
            f"mininetfed-node-executor "
            f"--file {shlex.quote(self.script)} "
            f"--node_id {shlex.quote(self.broker_id)} "
            f"--broker_addr {shlex.quote(broker_addr)} "
            f"--node_folder {DOCKER_NODE_FOLDER} "
            f"--node_args-json {args_json} "
            f"2> /flw/err.txt"
        )

        # Agora embrulha tudo em um bash -lc '<inner_cmd>'
        cmd = f"bash -lc {shlex.quote(inner_cmd)}"

        print(f"[FedBrokerNode] Abrindo terminal com: {cmd}")
        makeTerm(self, cmd=cmd)

        return Path("")
