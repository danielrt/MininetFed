import os
import shlex
import time
import json

from containernet.node import Docker
from containernet.node import DockerSensor

try:
    from containernet.term import makeTerm
except:
    from mininet.term import makeTerm

from federated.external_broker import ExtBroker

VOLUME_FOLDER = 'flw'
CPU_PERIOD = 100000
ENVS_FOLDER = 'envs'
DEFAULT_IMAGE = "mininetfed:container"
DEFAULT_IMAGE_6 = 'mininetfed:serversensor'


class color:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD_START = '\033[1m'
    BOLD_END = '\033[0m'
    RESET = "\x1B[0m"


class AutoStop (Docker):
    """Node that represents a docker container of a auto stoper.
    It stops the excecution of the local machine code waiting for a message from
    the mqtt topics:
        'minifed/stopQueue' or 'minifed/autoWaitContinue'
    """

    def __init__(self, name, dimage=DEFAULT_IMAGE, volumes=None, **kwargs):
        Docker.__init__(self, name, dimage=dimage, volumes=volumes, **kwargs)
        if volumes is None:
            volumes = []
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        self.broker_addr = broker_addr
        # Docker.start(self)
        self.cmd("route add default gw %s" % broker_addr)

    def auto_stop(self, verbose=False):
        try:
            self.cmd(
                f'bash -c "python3 stop.py {self.broker_addr}"', verbose=verbose)
        except:
            print(color.BLUE+"\nKeyboard interrupt: manual continue"+color.RESET)


class AutoStop6 (DockerSensor):
    """Node that represents a docker container of a MininerFed client.
    """

    def __init__(self, name, dimage=DEFAULT_IMAGE_6, volumes=None, **kwargs):
        if volumes is None:
            volumes = []
        self.name = name

        DockerSensor.__init__(self, name, dimage=dimage,
                              volumes=volumes, **kwargs)

        self.cmd("ifconfig eth0 down")

    def auto_stop(self, broker_addr, verbose=False):
        self.cmd("route add -A inet6 default gw  %s" %
                 broker_addr)
        try:
            self.cmd(f'bash -c "python3 stop.py {broker_addr}"', verbose=verbose)
        except:
            print(color.BLUE+"\nKeyboard interrupt: manual continue"+color.RESET)


class Broker (Docker):
    """Node that represents a docker container of a Mosquitto Broker.
    """

    def __init__(self, name, mode="internal", dimage=None, ext_broker_ip=None,
                 volumes=None, **kwargs):
        if volumes is None:
            volumes = []
        self.mode = mode

        if mode == "external" and ext_broker_ip is None:
            raise Exception("external broker ip needed to use external mode")
        elif mode != "internal" and mode != "external":
            raise Exception(f"'{mode}' is not a broker mode")

        kwargs["dimage"] = dimage
        kwargs["volumes"] = volumes
        Docker.__init__(self, name, **kwargs)

        self.cmd("iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")

    def run(self):
        if self.mode == "internal":
            makeTerm(
                self, cmd=f'bash -c "mosquitto -c {VOLUME_FOLDER}/util/mosquitto/mosquitto.conf"')
        elif self.mode == "external":
            self.ext = ExtBroker()
            self.ext.run_ext_brk()
        else:
            raise Exception(
                f"Invalid broker type:{self.general.get('broker')}")
        time.sleep(2)

    def terminate(self):
        Docker.terminate(self)
        if self.mode == "external":
            self.ext.stop_ext_brk()


class Client (Docker):
    """Node that represents a docker container of a MininerFed client.
    """

    def __init__(self, name, script, numeric_id, args=None, dimage=None,
                 cpu_quota=None, volumes=None, mem_limit=None, **kwargs):
        self.broker_addr = None
        self.experiment = None
        if args is None:
            args = {}
        if volumes is None:
            volumes = []
        self.name = name
        # self.trainer_mode = trainer_mode
        self.numeric_id = numeric_id
        self.script = script
        self.args = args

        if cpu_quota is not None:
            kwargs["cpu_period"] = CPU_PERIOD
            kwargs["cpu_quota"] = cpu_quota

        Docker.__init__(self, name, dimage=dimage,
                        volumes=volumes, mem_limit=mem_limit, **kwargs)

        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr, experiment_controller, args=None):
        self.experiment = experiment_controller
        self.broker_addr = broker_addr

        cmd = f"""bash -c "python3 {self.script} {self.broker_addr} {self.name} {self.numeric_id} {self.experiment.getClientFileName()} 2> {self.experiment.getClientFileName()}_err_{self.name}.txt """

        if self.args is not None and len(self.args) != 0:
            json_str = json.dumps(self.args).replace('"', '\\"')
            cmd += f"'{json_str}'"
        cmd += '" ;'

        self.cmd("route add default gw %s" %
                 self.broker_addr)

        makeTerm(self, cmd=cmd)


class ClientSensor (DockerSensor):
    """Node that represents a docker container of a MininerFed client."""
    def __init__(self, name, script, numeric_id, args=None, dimage=None,
                 cpu_quota=None, volumes=None, mem_limit=None, **kwargs):
        self.experiment = None
        self.broker_addr = None
        if volumes is None:
            volumes = []
        if args is None:
            args = {}
        self.name = name
        self.numeric_id = numeric_id
        self.script = script
        self.args = args

        if cpu_quota is not None:
            kwargs["cpu_period"] = CPU_PERIOD
            kwargs["cpu_quota"] = cpu_quota

        DockerSensor.__init__(self, name, dimage=dimage, volumes=volumes,
                              mem_limit=mem_limit, **kwargs)

        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr, experiment_controller):
        self.experiment = experiment_controller
        self.broker_addr = broker_addr

        cmd = f"""bash -c "python3 {self.script} {self.broker_addr} {self.name} {self.numeric_id} {self.experiment.getFileName()} 2> {VOLUME_FOLDER}/client_log/{self.experiment.getFileName()}_err.txt """

        if self.args is not None and len(self.args) != 0:
            json_str = json.dumps(self.args).replace('"', '\\"')
            cmd += f"'{json_str}'"
        cmd += '" ;'

        self.cmd("route add -A inet6 default gw  %s" %
                 self.broker_addr)
        #print(f"cmd:{cmd}")
        makeTerm(self, cmd=cmd)


class Monitor (Docker):
    """Node that represents a docker container of a custom network monitor.
    """

    def __init__(self, name, experiment_controller, script,
                 dimage=DEFAULT_IMAGE, volumes=None, **kwargs):
        if volumes is None:
            volumes = []
        self.script = script
        self.experiment = experiment_controller
        Docker.__init__(self, name, dimage=dimage,
                        volumes=volumes, **kwargs)
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr):
        self.broker_addr = broker_addr
        Docker.start(self)
        self.cmd("route add default gw %s" % self.broker_addr)
        command = f'bash -c "python3 {self.script} {self.broker_addr} {self.experiment.getFileName()}.net"'
        makeTerm(self, cmd=command)


class Server (Docker):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, name, script, args=None, dimage=None, cpu_quota=None,
                 volumes=None, mem_limit=None, **kwargs):
        self.broker_addr = None
        self.experiment = None
        if args is None:
            args = {}
        if volumes is None:
            volumes = []
        self.script = script
        self.args = args

        if cpu_quota is not None:
            kwargs["cpu_period"] = CPU_PERIOD
            kwargs["cpu_quota"] = cpu_quota

        Docker.__init__(self, name, dimage=dimage, volumes=volumes,
                        mem_limit=mem_limit, **kwargs)

        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr, experiment_controller, args=None):
        if args is None:
            args = {}
        self.experiment = experiment_controller
        self.broker_addr = broker_addr

        cmd = f"""bash -c "python3 {self.script} {self.broker_addr} {self.experiment.getFileName()} 2> {self.experiment.getFileName()}_err.txt """

        if self.args is not None and len(self.args) != 0:
            json_str = json.dumps(self.args).replace('"', '\\"')
            cmd += f"'{json_str}'"
        cmd += '" ;'
        self.cmd("route add default gw %s" %
                 self.broker_addr)

        makeTerm(self, cmd=cmd)


class ServerSensor (DockerSensor):
    """Node that represents a docker container of a MininerFed server."""
    def __init__(self, name, script, args=None, dimage=None, cpu_quota=None,
                 volumes=None, mem_limit=None, **kwargs):
        self.broker_addr = None
        self.experiment = None
        if args is None:
            args = {}
        if volumes is None:
            volumes = []
        self.script = script
        self.args = args

        if cpu_quota is not None:
            kwargs["cpu_period"] = CPU_PERIOD
            kwargs["cpu_quota"] = cpu_quota

        super().__init__(name, dimage=dimage,
                         volumes=volumes, mem_limit=mem_limit, **kwargs)

        self.cmd("iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")

    def run(self, broker_addr, experiment_controller):
        self.experiment = experiment_controller
        self.broker_addr = broker_addr
        cmd = f"""bash -c "python3 {self.script} {self.broker_addr} {self.experiment.getFileName()} 2> {self.experiment.getFileName()}_err.txt """

        if self.args is not None and len(self.args) != 0:
            json_str = json.dumps(self.args).replace('"', '\\"')
            cmd += f"'{json_str}'"
        cmd += '" ;'

        makeTerm(self, cmd=cmd)

    def auto_stop(self, verbose=False):
        try:
            self.cmd(
                f'bash -c "cd {VOLUME_FOLDER} && python3 stop.py {self.broker_addr}"', verbose=verbose)
        except:
            print(color.BLUE+"\nKeyboard interrupt: manual continue"+color.RESET)
