from mininetfed.core.fed_options import ServerOptions, ClientAcceptorType, ClientSelectorType, AggregatorType
from mininetfed.sim.net import MininetFed
from mininetfed.sim.nodes import FedServerNode, FedClientNode, FedBrokerNode
from mininetfed.sim.util.docker_utils import build_fed_node_docker_image

server_args = {
    ServerOptions.MIN_CLIENTS      : 4,
    ServerOptions.NUM_ROUNDS       : 100,
    ServerOptions.STOP_VALUE       : 0.98,
    ServerOptions.EARLY_STOP_VALUE : 10,
    ServerOptions.CLIENT_ACCEPTOR  : ClientAcceptorType.ALL_CLIENTS,
    ServerOptions.CLIENT_SELECTOR  : ClientSelectorType.ALL_CLIENTS,
    ServerOptions.MODEL_AGGREGATOR : AggregatorType.FED_AVG
}

def topology():

    client_dimage = build_fed_node_docker_image("basic_client", "client_code/client_requirements.txt")["tag"]

    net = MininetFed()
    try:
        s1 = net.addSwitch(name="s1", failMode='standalone')

        broker = net.addHost(name="broker", cls=FedBrokerNode)
        net.addLink(s1, broker)

        server = net.addHost(name="server", cls=FedServerNode, server_args=server_args)
        net.addLink(s1, server)

        clients = []
        for i in range(4):
            c = net.addHost(name=f'client{i}', cls=FedClientNode, script="mnist_trainer.py", dimage=client_dimage, client_folder=f"clients/client{i}")
            net.addLink(s1, c)
            clients.append(c)

        print('*** Starting network...\n')
        net.build()
        net.addNAT(name='nat0', linkTo='s1', ip='192.168.210.254').configDefault()
        s1.start([])

        net.runFed()
    finally:
        # isso garante limpeza mesmo se der exceção no meio
        net.stop()

if __name__ == '__main__':
    topology()
