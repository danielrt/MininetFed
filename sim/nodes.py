import json
import os

from containernet.node import Docker
from containernet.term import makeTerm
from docker.errors import ImageNotFound

from sim.docker_image_builder import docker_image_exists, build_fed_broker_docker_image, build_fed_node_docker_image


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

    def run(self, broker_addr):
        pass

class FedServerNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, node_id : str, script: str, server_folder : str, dimage = None, server_args : dict | None = None):
        super().__init__( node_id = node_id, script = script, node_folder = server_folder, dimage = dimage, node_args = server_args)
        self.cmd("ifconfig eth0 down")
        # TODO: quando script não for passado como parametro, tem que executar a classe FedServer do Sim

    def run(self, broker_addr):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.node_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.args)}  2> err.txt """
        self.cmd("route add default gw %s" % broker_addr)
        os.umask(0o000)
        makeTerm(self, cmd=cmd)

class FedClientNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, node_id : str, script: str, client_folder : str, dimage, client_args : dict | None = None):
        super().__init__( node_id = node_id, script = script, node_folder = client_folder, dimage = dimage, node_args = client_args)
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        cmd = f"""bash -c "umask 000; fed_node_executor --file {self.script} --node_id {self.node_id} --broker_addr {broker_addr} --node_args-json {json.dumps(self.args)}  2> err.txt """
        self.cmd("route add default gw %s" % broker_addr)
        makeTerm(self, cmd=cmd)

class FedBrokerNode(DockerFedNode):
    """Node that represents a docker container of a MininerFed broker."""
    def __init__(self, broker_id : str, script: str, broker_folder : str, dimage, broker_args : dict | None = None):
        super().__init__( node_id = broker_id, script = script, node_folder = broker_folder, dimage = dimage, node_args = broker_args)
        self.cmd("iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")

    def run(self, broker_addr):
        if self.args["external"]:
            self.cmd('sh -c "echo \'persistence false\nlog_dest stdout\nallow_anonymous true\nlistener 10.0.0.1:1883\nsys_interval 5\' > /mosq.conf && mosquitto -c /mosq.conf"')
        else:
            self.cmd('sh -c "echo \'persistence false\nlog_dest stdout\nallow_anonymous true\nconnection_messages true\nlistener 1883\nsys_interval 5\' > /mosq.conf && mosquitto -c /mosq.conf"')
