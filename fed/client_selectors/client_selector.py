from abc import abstractmethod

from fed.client_state import ClientState


class ClientSelector:

    @abstractmethod
    def select_clients(self, clients_states : list[ClientState]) -> list[str]:
        pass