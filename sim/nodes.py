import json
import os

from containernet.node import Docker
from containernet.term import makeTerm
from docker.errors import ImageNotFound

from sim.docker_image_builder import docker_image_exists

class DockerFedNode(Docker):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, node_id : str, script: str, node_folder : str, dimage, node_args : dict | None = None):
        self.script = script
        self.node_id = node_id
        self.args = node_args or {}
        self.node_folder = node_folder

        # Evita colisão de parâmetros (ex.: se alguém passou 'volumes' dentro de self.args)
        safe_args = dict(self.args)
        safe_args.pop("volumes", None)
        safe_args.pop("name", None)
        safe_args.pop("dimage", None)

        volumes = [f"{node_folder}:/flw:rw"]

        if not docker_image_exists(dimage):
            raise ImageNotFound(f"Image Docker {dimage} was not found.")

        Docker.__init__(self, name=self.node_id, dimage=dimage, volumes=volumes, **safe_args)

        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.node_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.args)}  2> err.txt """
        self.cmd("route add default gw %s" % broker_addr)
        os.umask(0o000)
        makeTerm(self, cmd=cmd)

class FedServerNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, node_id : str, script: str, node_folder : str, dimage, node_args : dict | None = None):
        super().__init__( node_id = node_id, script = script, node_folder = node_folder, dimage = dimage, node_args = node_args)

    def run(self, broker_addr):
        super().run(broker_addr)

class FedClientNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, node_id : str, script: str, node_folder : str, dimage, node_args : dict | None = None):
        super().__init__( node_id = node_id, script = script, node_folder = node_folder, dimage = dimage, node_args = node_args)

    def run(self, broker_addr):
        super().run(broker_addr)