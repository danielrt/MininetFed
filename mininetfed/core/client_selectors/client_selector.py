from abc import abstractmethod

from mininetfed.core.dto.client_state import ClientState



class ClientSelector:

    @abstractmethod
    def select_clients(self, clients_states : list[ClientState]) -> list[str]:
        pass