from fed.client_acceptors.client_acceptor import ClientAcceptor
from fed.client_info import ClientInfo

class AllClientsAcceptor(ClientAcceptor):
    def accept(self, client_info : ClientInfo) -> bool:
        return True