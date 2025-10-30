from abc import abstractmethod

from fed.client_info import ClientInfo


class ClientAcceptor:

    @abstractmethod
    def accept(self, client_info : ClientInfo) -> bool:
        pass