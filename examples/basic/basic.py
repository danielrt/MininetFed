from mininetfed.core.dto.metrics import MetricType
from mininetfed.core.fed_options import ServerOptions, ClientAcceptorType, ClientSelectorType, AggregatorType
from mininetfed.sim.net import MininetFed
from mininetfed.sim.nodes import FedServerNode, FedClientNode, FedBrokerNode
from mininetfed.sim.util.clients_generator import create_federated_client_datasets
from mininetfed.sim.util.docker_utils import build_fed_node_docker_image

n_clients = 4
client_code_path = "client_code/"

server_args = {
    ServerOptions.MIN_CLIENTS      : n_clients,
    ServerOptions.NUM_ROUNDS       : 100,
    ServerOptions.TARGET_METRIC    : MetricType.ACCURACY,
    ServerOptions.STOP_VALUE       : 0.98,
    ServerOptions.PATIENT          : 10,
    ServerOptions.CLIENT_ACCEPTOR  : ClientAcceptorType.ALL_CLIENTS,
    ServerOptions.CLIENT_SELECTOR  : ClientSelectorType.ALL_CLIENTS,
    ServerOptions.MODEL_AGGREGATOR : AggregatorType.FED_AVG
}



def configure_experiment():

    client_paths = create_federated_client_datasets(
        dataset_source="openml:mnist_784",
        target_col="class",
        n_clients=n_clients,
        split_mode="iid",
        code_src_dir=client_code_path,
        openml_version=1,
    )

    client_dimage = build_fed_node_docker_image("basic_client", client_code_path + "client_requirements.txt")["tag"]


    net = MininetFed()
    try:
        s1 = net.addSwitch(name="s1", failMode='standalone')

        broker = net.addHost(name="broker", cls=FedBrokerNode)
        net.addLink(s1, broker)

        server = net.addHost(name="server", cls=FedServerNode, server_args=server_args)
        net.addLink(s1, server)

        clients = []
        for i in range(n_clients):
            c = net.addHost(name=f'client{i}', cls=FedClientNode, script="mnist_trainer.py", dimage=client_dimage, client_folder=client_paths[i])
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
    configure_experiment()
