from abc import abstractmethod

from mininetfed.core.dto.client_info import ClientInfo

class ClientAcceptorType:
    ALL_CLIENTS = "all_clients"

class ClientAcceptor:

    @abstractmethod
    def accept(self, client_info : ClientInfo) -> bool:
        pass