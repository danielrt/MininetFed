import os
import re
from datetime import datetime


class Client:
    def __init__(self):
        self.t_arrival = 0
        self.events = {}

class Server:
    def __init__(self):
        self.events = {}
        self.clients = {}

class Round:
    def __init__(self, round_id):
        self.round_id = round_id
        self.duration = 0
        self.arrival_min_clients = None
        self.arrival_actual_clients = None
        self.server = Server()
        self.clients = {}


def process_log_line(line):
    timestamp_str, content = line.split(" - ", 1)
    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
    parts = content.split()
    tag = parts[0]
    extras = parts[1:]
    
    return tag, timestamp, extras


def ler_logs(logs_path):
    """
    Lê os arquivos de log e popula as classes Round, Server e Client.

    Args:
        pasta_principal (str): O caminho para a pasta principal que contém
                               spn.log e a subpasta client_logs.

    Returns:
        dict: Um dicionário onde as chaves são os IDs dos rounds e os valores
              são objetos da classe Round.
    """
    rounds = {}

    spn_log_path = os.path.join(logs_path, 'spn.log')
    client_logs_dir = os.path.join(logs_path, 'client_logs')

    # 1. Leitura do arquivo spn.log (logs do servidor)
    if os.path.exists(spn_log_path):
        with open(spn_log_path, 'r') as f:
            for line in f:
                # O parsing agora é mais detalhado para cada tipo de tag
                tag, timestamp, extras = process_log_line(line)
                if timestamp and tag:
                    processar_evento_server(rounds, timestamp, tag, extra_data)

    # 2. Leitura dos arquivos de log dos clientes
    if os.path.exists(client_logs_dir):
        for filename in os.listdir(client_logs_dir):
            if filename.endswith('_spn.log'):
                client_id = filename.split('_')[0]
                client = Client(client_id)
                filepath = os.path.join(client_logs_dir, filename)

                with open(filepath, 'r') as f:
                    for linha in f:
                        # Adapte o parsing do cliente se necessário
                        timestamp, tag = parse_linha_client(linha)
                        if timestamp and tag:
                            client.eventos.append(EventoLog(timestamp, tag))

                if client.eventos:
                    processar_evento_client(rounds, client)

    return rounds
