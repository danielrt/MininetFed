from abc import abstractmethod

from mininetfed.core.dto.client_state import ClientState

class ClientSelectorType:
    ALL_CLIENTS = "all_clients"

class ClientSelector:

    @abstractmethod
    def select_clients(self, clients_states : list[ClientState]) -> list[str]:
        pass