import os
import shutil
import stat

from pathlib import Path
from datetime import datetime

from federated.node import VOLUME_FOLDER


class Experiment:
    def __init__(self, experiments_folder, experiment_name):
        self.path = None
        self.local_path = None
        self.client_path = None
        self.client_local_path = None
        self.name = experiment_name
        self.experiments_folder = experiments_folder
        self.create_log_folders()

    def create_log_folders(self):
        # Salve a máscara atual
        old_mask = os.umask(0o000)

        now_str = datetime.now().strftime("%Hh%Mm%Ss")

        self.local_path = f"{self.experiments_folder}/{self.name}/{now_str}"
        self.client_local_path = f"{self.local_path}/client_logs"

        Path(self.local_path).mkdir(parents=True, exist_ok=True)
        Path(self.client_local_path).mkdir(parents=True, exist_ok=True)

        # Change folder permissions to 777
        os.chmod(self.local_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        os.chmod(self.client_local_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        self.path = f"{VOLUME_FOLDER}/{self.local_path}"
        self.client_path = f"{VOLUME_FOLDER}/{self.client_local_path}"

        # Restaure a máscara original
        os.umask(old_mask)

    def change_permissions(self):
        # Salve a máscara atual
        old_mask = os.umask(0o000)

        for root, dirs, files in os.walk(self.path):
            for file in files:
                path = os.path.join(root, file)
                os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        # Restaure a máscara original
        os.umask(old_mask)

    def get_logs_path(self):
        return self.path

    def get_logs_local_path(self):
        return self.local_path

    def get_client_logs_path(self):
        return self.client_path

    def get_client_logs_local_path(self):
        return self.client_local_path

    def copy_file_to_experiment_folder(self, file_name=''):
        just_the_file_name = Path(file_name).name
        os.umask(0o000)
        shutil.copyfile(file_name, f'{self.get_logs_local_path()}/{just_the_file_name}')
