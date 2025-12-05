import json
import os
import tempfile
import textwrap
from pathlib import Path

from containernet.node import Docker
from containernet.term import makeTerm
from docker.errors import ImageNotFound

from mininetfed.sim.util.docker_utils import docker_image_exists, build_fed_broker_docker_image, \
    build_fed_node_docker_image, MININETFED_IMAGE_INSTALL_LOCATION


class DockerFedNode(Docker):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, name : str, node_folder : str, dimage : str, **kwargs):

        volumes = [f"{node_folder}:/flw:rw"]

        if not dimage:
            raise ImageNotFound(f"No Image Docker was provided.")

        if not docker_image_exists(dimage):
            raise ImageNotFound(f"Image Docker {dimage} was not found.")

        Docker.__init__(self, name=name, dimage=dimage, volumes=volumes, **kwargs)

    def run(self, broker_addr):
        pass

class FedClientNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, name : str, script: str, client_folder : str, dimage : str | None = None, client_args : dict | None = None, **kwargs):
        super().__init__(name= name, node_folder = client_folder, dimage = dimage, **kwargs)
        self.script = script
        self.client_id = name
        self.client_args = client_args or {}
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.client_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.client_args)}  2> err.txt """
        self.cmd("route add default gw %s" % broker_addr)
        makeTerm(self, cmd=cmd)

class FedServerNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, name : str, script: str | None = None, server_folder : str | None = None, dimage : str | None = None, server_args : dict | None = None, **kwargs):
        self.server_id = name
        # quando script não for passado como parametro, tem que executar o no server implementacao padrao
        self.script = script or MININETFED_IMAGE_INSTALL_LOCATION + "/core/nodes/default_fed_server.py"
        self.server_folder = server_folder or Path.cwd() / "server_output"
        if not server_folder or len(server_folder):
            self.server_folder.mkdir(exist_ok=True)
        self.server_args = server_args or {}

        server_docker_image = dimage
        if not server_docker_image:
            with tempfile.NamedTemporaryFile("w", delete=False) as f:
                default_server_requirements = textwrap.dedent("""
                    numpy
                    paho-mqtt
                """).strip()
                f.write(default_server_requirements)
                server_docker_image = build_fed_node_docker_image("server", f.name)["tag"]

        super().__init__(name= name, node_folder = server_folder, dimage = server_docker_image, **kwargs)
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.server_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.args)}  2> err.txt """
        self.cmd("route add default gw %s" % broker_addr)
        os.umask(0o000)
        makeTerm(self, cmd=cmd)

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

        super().__init__(name= name, node_folder = broker_folder, dimage = broker_docker_image, **kwargs)
        self.cmd("iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")

    def run(self, broker_addr = ""):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.broker_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.broker_args)}  2> err.txt """
        makeTerm(self, cmd=cmd)
