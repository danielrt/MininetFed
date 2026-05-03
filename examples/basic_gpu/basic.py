from mininetfed.core.dto.metrics import MetricType
from mininetfed.core.fed_options import (
    ServerOptions,
    ClientAcceptorType,
    ClientSelectorType,
    AggregatorType,
)
from mininetfed.sim.net import MininetFed
from mininetfed.sim.nodes import FedServerNode, FedClientNode, FedBrokerNode
from mininetfed.sim.util.clients_generator import create_federated_client_datasets
from mininetfed.sim.util.docker_utils import build_fed_node_docker_image

# ============================================================
# Configurações gerais
# ============================================================

USE_GPU = True
N_CLIENTS = 4
CLIENT_CODE_PATH = "client_code/"
CLIENT_REQUIREMENTS = CLIENT_CODE_PATH + "client_requirements.txt"

server_args = {
    ServerOptions.MIN_CLIENTS: N_CLIENTS,
    ServerOptions.NUM_ROUNDS: 100,
    ServerOptions.TARGET_METRIC: MetricType.ACCURACY,
    ServerOptions.STOP_VALUE: 0.98,
    ServerOptions.PATIENT: 10,
    ServerOptions.CLIENT_ACCEPTOR: ClientAcceptorType.ALL_CLIENTS,
    ServerOptions.CLIENT_SELECTOR: ClientSelectorType.ALL_CLIENTS,
    ServerOptions.MODEL_AGGREGATOR: AggregatorType.FED_AVG,
}


def configure_experiment():
    client_paths = create_federated_client_datasets(
        dataset_source="openml:mnist_784",
        target_col="class",
        n_clients=N_CLIENTS,
        split_mode="iid",
        code_src_dir=CLIENT_CODE_PATH,
        openml_version=1,
    )

    # Imagem dos clientes com suporte a GPU.
    # Requer docker_utils.py com build_fed_node_docker_image(..., use_gpu=True).
    client_dimage = build_fed_node_docker_image(
        "basic_client",
        requirements_file=CLIENT_REQUIREMENTS,
        use_gpu=USE_GPU,
    )["tag"]

    net = MininetFed()

    try:
        s1 = net.addSwitch(name="s1", failMode="standalone")

        broker = net.addHost(
            name="broker",
            cls=FedBrokerNode,
        )
        net.addLink(s1, broker)

        # O servidor normalmente não precisa de GPU para FedAvg.
        # Se quiser testar GPU no servidor também, troque use_gpu=False por use_gpu=USE_GPU.
        server = net.addHost(
            name="server",
            cls=FedServerNode,
            server_args=server_args,
            use_gpu=False,
        )
        net.addLink(s1, server)

        clients = []
        for i in range(N_CLIENTS):
            client = net.addHost(
                name=f"client{i}",
                cls=FedClientNode,
                script="mnist_trainer.py",
                dimage=client_dimage,
                client_folder=client_paths[i],
                use_gpu=USE_GPU,
            )
            net.addLink(s1, client)
            clients.append(client)

        print("*** Starting network...\n")
        print(f"*** GPU habilitada para clientes: {USE_GPU}\n")
        print(f"*** Imagem dos clientes: {client_dimage}\n")

        net.build()
        net.addNAT(name="nat0", linkTo="s1", ip="192.168.210.254").configDefault()
        s1.start([])

        net.runFed(show_term=True)

    finally:
        net.stop()


if __name__ == "__main__":
    configure_experiment()