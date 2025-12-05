from abc import abstractmethod

from mininetfed.core.dto.client_info import ClientInfo



class ClientAcceptor:

    @abstractmethod
    def accept(self, client_info : ClientInfo) -> bool:
        pass