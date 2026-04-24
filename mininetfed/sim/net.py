from time import sleep

from containernet.net import Containernet

from mininetfed.sim.nodes import FedBrokerNode, FedClientNode, FedServerNode


class MininetFed(Containernet):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.nodes = []
        self.broker = None
        self.broker_name = ""

    def addHost(self, name, cls=None, **params):
        n = super().addHost(name, cls, **params)
        if cls is not None and isinstance(cls, type) and issubclass(cls, FedBrokerNode):
            if self.broker:
                raise RuntimeError("Only one FedBrokerNode is allowed.")
            self.broker = n
            self.broker_name = name
        elif cls is not None and isinstance(cls, type) and (issubclass(cls, FedServerNode) or issubclass(cls, FedClientNode)):
            self.nodes.append(n)
        return n

    def runFed(self):
        if not self.broker:
            raise RuntimeError("You must add a FedBrokerNode to the net.")

        self.broker.run()
        broker_address = self.broker.IP(intf=f"{self.broker_name}-eth0")

        done_files = []
        for node in self.nodes:
            done_files.append(node.run(broker_addr=broker_address))

        # Espera todos os nodes
        for done in done_files:
            while not done.exists():
                sleep(1)

        # exclui os arquivos
        for done in done_files:
            done.unlink(missing_ok=True)
