import csv
import os
import sys
from datetime import datetime


class Client:
    def __init__(self, client_id):
        self.client_id = client_id
        self.t_arrival = 0
        self.rounds = []

class Server:
    def __init__(self):
        self.arrival_min_clients = 0
        self.arrival_actual_clients = 0
        self.clients = {}
        self.rounds = []

class Round:
    def __init__(self, round_id):
        self.round_id = round_id
        self.events = {}
        self.round_duration = 0

class Experiment:
    def __init__(self):
        self.server = Server()
        self.clients = []
        self.server_metrics = {'ROUND_DURATION' : 0.0, 'T_SELECT' : 0.0, 'T_RETURN' : 0.0, 'T_AGGREG' : 0.0, 'T_SAVE' : 0.0, 'T_COMPUTE' : 0.0}
        self.clients_metrics = {}
        self.clients_metrics_avg = {'ROUND_DURATION' : 0.0, 'T_SELECT' : 0.0, 'T_SEND' : 0.0, 'T_TRAIN' : 0.0, 'T_RETURN' : 0.0}


    def save_spn_metrics(self, path):
        self.save_server_csv(path)
        self.save_clients_csv(path)
        self.save_summary(path)

    def save_server_csv(self, path):
        data_csv = []
        data_coluns = ['ROUND', 'ROUND_DURATION', 'T_SELECT', 'T_RETURN', 'T_AGGREG', 'T_SAVE', 'T_COMPUTE' ]
        data_csv.append(data_coluns)
        server_rounds = self.server.rounds
        n_rounds = len(server_rounds)
        for server_round in server_rounds:
            round_id = server_round.round_id
            round_duration = server_round.round_duration * 1000
            self.server_metrics['ROUND_DURATION'] += round_duration
            t_select = abs((server_round.events['T_SELECT_END'][0] - server_round.events['T_SELECT_START'][0]).total_seconds() * 1000)
            self.server_metrics['T_SELECT'] += t_select
            t_return_0 = abs((server_round.events['T_RETURN_0_END'][0] - server_round.events['T_RETURN_0_START'][0]).total_seconds() * 1000)
            t_return_1 = abs((server_round.events['T_RETURN_1_END'][0] - server_round.events['T_RETURN_1_START'][0]).total_seconds() * 1000)
            t_return = t_return_0 + t_return_1
            self.server_metrics['T_RETURN'] += t_return
            t_aggreg = abs((server_round.events['T_AGGREG_END'][0] - server_round.events['T_AGGREG_START'][0]).total_seconds() * 1000)
            self.server_metrics['T_AGGREG'] += t_aggreg
            t_save = abs((server_round.events['T_SAVE_END'][0] - server_round.events['T_SAVE_START'][0]).total_seconds() * 1000)
            self.server_metrics['T_SAVE'] += t_save
            t_compute = round_duration - t_select - t_return - t_aggreg - t_save
            self.server_metrics['T_COMPUTE'] += t_compute
            data_csv.append([round_id, round_duration, t_select, t_return, t_aggreg, t_save, t_compute])

        for key in self.server_metrics.keys():
            self.server_metrics[key] = self.server_metrics[key] / n_rounds

        csv_file_path = os.path.join(path, 'server.csv')
        with open(csv_file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(data_csv)

    def save_clients_csv(self, path):
        data_csv = []
        data_coluns = ['ROUND', 'CLIENT_ID', 'ROUND_DURATION', 'T_SELECT', 'SELECTED', 'T_SEND', 'T_TRAIN', 'TRAINED', 'T_RETURN' ]
        data_csv.append(data_coluns)
        for client in self.clients:
            client_id = client.client_id
            self.clients_metrics[client_id] = {'ROUND_DURATION' : 0.0, 'T_SELECT' : 0.0, 'T_SEND' : 0.0, 'T_TRAIN' : 0.0, 'T_RETURN' : 0.0}
            n_rounds = len(client.rounds)
            for client_round in client.rounds:
                round_id =  client_round.round_id
                round_duration = client_round.round_duration.total_seconds() * 1000
                self.clients_metrics[client_id]['ROUND_DURATION'] += round_duration
                t_select = abs((client_round.events['T_SELECT'][0] - self.server.clients[client_id].rounds[round_id].events['T_SELECT'][0]).total_seconds() * 1000)
                self.clients_metrics[client_id]['T_SELECT'] += t_select
                selected = client_round.events['T_SELECT'][1]
                t_send = abs((client_round.events['T_SEND'][0] - self.server.rounds[round_id].events['T_SEND'][0]).total_seconds() * 1000)
                self.clients_metrics[client_id]['T_SEND'] += t_send
                t_train = float(client_round.events['T_TRAIN'][2]) * 1000.0
                self.clients_metrics[client_id]['T_TRAIN'] += t_train
                trained = client_round.events['T_TRAIN'][1]
                t_return_0 = abs((client_round.events['T_RETURN_0'][0] - self.server.clients[client_id].rounds[round_id].events['T_RETURN_0'][0]).total_seconds() * 1000)
                t_return_1 = abs((client_round.events['T_RETURN_1'][0] - self.server.clients[client_id].rounds[round_id].events['T_RETURN_1'][0]).total_seconds() * 1000)
                t_return = (t_return_0 + t_return_1) / 2.0
                self.clients_metrics[client_id]['T_RETURN'] += t_return
                data_csv.append([round_id, client_id, round_duration, t_select, selected, t_send, t_train, trained, t_return])

            for key in self.clients_metrics[client_id].keys():
                self.clients_metrics[client_id][key] = self.clients_metrics[client_id][key] / n_rounds

        n_clients = len(self.clients)
        for client_id in self.clients_metrics:
            for client_metric in self.clients_metrics[client_id]:
                self.clients_metrics_avg[client_metric] += self.clients_metrics[client_id][client_metric]

        for client_metric in self.clients_metrics_avg:
            self.clients_metrics_avg[client_metric] = self.clients_metrics_avg[client_metric] / n_clients

        csv_file_path = os.path.join(path, 'clients.csv')

        with open(csv_file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(data_csv)

    def save_summary(self, path):
        with open(os.path.join(path, 'summary.txt'), 'w', newline='') as f:
            f.write(f'N_CLIENTS: {len(self.clients)}\n')
            f.write(f'N_ROUNDS: {len(self.server.rounds)}\n\n')
            f.write(f'SERVER METRICS:\n')
            for server_metric in self.server_metrics:
                f.write(f'\t{server_metric}: {self.server_metrics[server_metric]}\n')
            f.write(f'\nCLIENT METRICS:\n')
            for client_metric in self.clients_metrics_avg:
                f.write(f'\t{client_metric}: {self.clients_metrics_avg[client_metric]}\n')
            f.write(f'\nCLIENT METRICS BY CLIENT:\n')
            for client in self.clients_metrics:
                f.write(f'\t\t{client}:\n')
                for client_metric in self.clients_metrics[client]:
                    f.write(f'\t\t\t{client_metric}: {self.clients_metrics[client][client_metric]}\n')

def process_log_line(line):
    timestamp_str, content = line.split(" - ", 1)
    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
    parts = content.split()
    tag = parts[0]
    extras = parts[1:]
    return tag, timestamp, extras

def read_spn_logs(spn_logs_path):
    server_spn_log_path = os.path.join(spn_logs_path, 'spn.log')
    clients_spn_logs_dir = os.path.join(spn_logs_path, 'client_logs')

    experiment = Experiment()

    # 1. Leitura do arquivo spn.log (logs do servidor)
    if os.path.exists(server_spn_log_path):
        server = experiment.server
        with open(server_spn_log_path, 'r') as f:
            round_id = 0
            for line in f:
                tag, timestamp, extras = process_log_line(line)
                if tag == 'T_ARRIVAL':
                    client_id = extras[0]
                    if not client_id in server.clients:
                        client = Client(client_id)
                        server.clients[client_id] = client
                    client = server.clients[client_id]
                    client.t_arrival = timestamp
                if tag == 'T_ARRIVAL_END':
                    server.arrival_min_clients = extras[0]
                    server.arrival_actual_clients = extras[1]
                if tag == 'START_ROUND':
                    round_id = int(extras[0])
                    server_round = Round(round_id)
                    server.rounds.append(server_round)
                if tag == 'T_SELECT_START':
                    server.rounds[round_id].events[tag] = [timestamp]
                if tag == 'T_SELECT':
                    client_id = extras[0]
                    client = server.clients[client_id]
                    if round_id >= len(client.rounds):
                        client.rounds.append(Round(round_id))
                    client_round = client.rounds[round_id]
                    client_round.events[tag] = [timestamp, extras[1]]
                if tag == 'T_SELECT_END':
                    server.rounds[round_id].events[tag] = [timestamp, extras[0]]
                if tag == 'T_RETURN_0_START':
                    server.rounds[round_id].events[tag] = [timestamp]
                if tag == 'T_RETURN_0':
                    client_id = extras[0]
                    client = server.clients[client_id]
                    if round_id >= len(client.rounds):
                        client.rounds.append(Round(round_id))
                    client_round = client.rounds[round_id]
                    client_round.events[tag] = [timestamp, extras[1]]
                if tag == 'T_RETURN_0_END':
                    server.rounds[round_id].events[tag] = [timestamp, extras[0]]
                if tag == 'T_AGGREG_START':
                    server.rounds[round_id].events[tag] = [timestamp]
                if tag == 'T_AGGREG_END':
                    server.rounds[round_id].events[tag] = [timestamp]
                if tag == 'T_SEND':
                    server.rounds[round_id].events[tag] = [timestamp]
                if tag == 'T_RETURN_1_START':
                    server.rounds[round_id].events[tag] = [timestamp]
                if tag == 'T_RETURN_1':
                    client_id = extras[0]
                    client = server.clients[client_id]
                    if round_id >= len(client.rounds):
                        client.rounds.append(Round(round_id))
                    client_round = client.rounds[round_id]
                    client_round.events[tag] = [timestamp]
                if tag == 'T_RETURN_1_END':
                    server.rounds[round_id].events[tag] = [timestamp, extras[0]]
                if tag == 'T_SAVE_START':
                    server.rounds[round_id].events[tag] = [timestamp]
                if tag == 'T_SAVE_END':
                    server.rounds[round_id].events[tag] = [timestamp]
                if tag == 'ROUND_DURATION':
                    server.rounds[round_id].round_duration = float(extras[0])
                if tag == 'END_ROUND':
                    round_id = round_id + 1

        # 2. Leitura dos arquivos de log dos clientes
        if os.path.exists(clients_spn_logs_dir):
            for filename in os.listdir(clients_spn_logs_dir):
                if filename.endswith('_spn.log'):
                    client_id = filename.split('_')[0]
                    filepath = os.path.join(clients_spn_logs_dir, filename)

                    with open(filepath, 'r') as f:
                        round_id = 0
                        round_time_init = 0
                        client = Client(client_id)
                        experiment.clients.append(client)
                        for line in f:
                            tag, timestamp, extras = process_log_line(line)
                            if tag == 'T_ARRIVAL':
                                client.t_arrival = timestamp
                            if tag == 'START_ROUND':
                                round_time_init =timestamp
                                round_id = int(extras[0])
                                client_round = Round(round_id)
                                client.rounds.append(client_round)
                                client_round.events[tag] = [timestamp]
                            if tag == 'T_SELECT':
                                client.rounds[round_id].events[tag] = [timestamp, extras[0]]
                            if tag == 'T_TRAIN':
                                client.rounds[round_id].events[tag] = [timestamp, extras[0], extras[1]]
                            if tag == 'T_RETURN_0':
                                client.rounds[round_id].events[tag] = [timestamp]
                            if tag == 'T_SEND':
                                client.rounds[round_id].events[tag] = [timestamp]
                            if tag == 'T_RETURN_1':
                                client.rounds[round_id].events[tag] = [timestamp]
                            if tag == 'END_ROUND':
                                client.rounds[round_id].round_duration = timestamp - round_time_init

    else:
        return None
    return experiment

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else print("correct use: python spn_log_extractor.py <path_to_logs>")
    experiment = read_spn_logs(path)
    if experiment:
        experiment.save_spn_metrics(path)
    else:
        print("The provided path does not contain valid log files")