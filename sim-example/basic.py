from sim.docker_image_builder import build_fed_node_docker_image
from sim.net import MininetFed
from sim.nodes import FedServerNode, FedClientNode

current_dir = os.path.dirname(os.path.abspath(__file__))
volume = "/flw"
volumes = [f"{Path.cwd()}:" + volume, "/tmp/.X11-unix:/tmp/.X11-unix:rw",
           "{}/client:/client".format(current_dir), "{}/server:/server".format(current_dir)]
experiment_config = {
    "ipBase": "10.0.0.0/24",
    "experiments_folder": "experiments",
    "experiment_name": "basic"
}
# See server/client_selection.py for the available client_selector models
server_args = {"min_trainers": 16, "num_rounds": 100, "stop_acc": 0.999,
               'client_selector': 'All', 'aggregator': "FedAvg"}


def topology():

    build_fed_node_docker_image()

    net = MininetFed()

    s1 = net.addSwitch("s1", failMode='standalone')

    srv1 = net.addHost('srv1', cls=FedServerNode, script="server/server.py",
                       args=server_args, volumes=volumes,
                       dimage='mininetfed:server')
    clients = []
    for i in range(16):
        clients.append(net.addHost(f'sta{i}', cls=FedClientNode, script="client/client.py",
                                   args=client_args, volumes=volumes,
                                   dimage='mininetfed:client_tf_cuda', numeric_id=i))

    info('*** Connecting to the MininetFed Devices...\n')
    net.connectMininetFedDevices()

    info('*** Creating links...\n')
    net.addLink(srv1, s1)
    for client in clients:
        net.addLink(client, s1)

    info('*** Starting network...\n')
    net.build()
    net.addNAT(name='nat0', linkTo='s1', ip='192.168.210.254').configDefault()
    s1.start([])

    info('*** Running FL internal devices...\n')
    net.runFlDevices()

    srv1.run(broker_addr=net.broker_addr,
             experiment_controller=net.experiment_controller)

    sleep(3)
    for client in clients:
        client.run(broker_addr=net.broker_addr,
                   experiment_controller=net.experiment_controller)

    info('*** Running Autostop...\n')
    net.wait_experiment(start_cli=False)

    info('*** Stopping network...\n')
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    topology()
