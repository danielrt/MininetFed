import os
import shutil
import stat

from pathlib import Path
from datetime import datetime
from federated.node import VOLUME_FOLDER


class Experiment:
    def __init__(self, experiments_folder, experiment_name, create_new=True):
        self.path = None
        self.client_local_path = "client_log"
        self.client_path = f"{VOLUME_FOLDER}/{self.client_local_path}"
        self.now = datetime.now()
        self.local_path = None
        self.name = experiment_name
        self.experiments_folder = experiments_folder
        self.create_new = create_new
        self.create_client_log_folder()
        self.create_folder()

    def create_client_log_folder(self):
        path = Path(self.client_local_path)
        if not path.exists():
            os.makedirs(path)

    def create_folder(self):
        # Salve a máscara atual
        old_mask = os.umask(0o000)

        if self.create_new:
            today_str = self.now.strftime("%Y_%m_%d_")
            self.local_path = f"{self.experiments_folder}/{today_str}{self.name}"
        else:
            self.local_path = f"{self.experiments_folder}/{self.name}"
        Path(self.local_path).mkdir(parents=True, exist_ok=True)

        # Change folder permissions to 777
        os.chmod(self.local_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        self.path = f"{VOLUME_FOLDER}/{self.local_path}"
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

    def getFileName(self, extension=""):
        now_str = self.now.strftime("%Hh%Mm%Ss")
        return f"{self.path}/{now_str}{self.name}{extension}"

    def getFileNameLocal(self, extension=""):
        now_str = self.now.strftime("%Hh%Mm%Ss")
        return f"{self.local_path}/{now_str}{self.name}{extension}"

    def getClientFileName(self):
        now_str = self.now.strftime("%Hh%Mm%Ss")
        return f"{self.client_path}/{now_str}{self.name}"

    def getClientFileNameLocal(self):
        now_str = self.now.strftime("%Hh%Mm%Ss")
        return f"{self.client_local_path}/{now_str}{self.name}"

    def copyFileToExperimentFolder(self, file_name=''):
        shutil.copyfile(file_name, self.getFileNameLocal(
            extension=f".{file_name.split('.')[1]}"))
