from mininetfed.core.client_selectors.client_selector import ClientSelector
from mininetfed.core.dto.client_state import ClientState

class AllClientsSelector(ClientSelector):
    def select_clients(self, clients_states: list[ClientState]) -> list[str]:
        selected_clients = []
        for client_state in clients_states:
            selected_clients.append(client_state.get_client_id())
        return selected_clients