import os

# Reduz logs do TensorFlow. Precisa vir antes de importar tensorflow.
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np
import pandas as pd
import tensorflow as tf

from tensorflow.keras.utils import to_categorical
from tensorflow.keras.layers import Conv2D, MaxPool2D, Flatten, Dense
from tensorflow.keras.optimizers import SGD
from tensorflow.keras.models import Sequential

from sklearn.metrics import confusion_matrix
from sklearn.model_selection import train_test_split

from mininetfed.core.dto.client_info import ClientInfo
from mininetfed.core.dto.dataset_info import DatasetInfo
from mininetfed.core.dto.metrics import Metrics, MetricType
from mininetfed.core.nodes.fed_client import FedClient
from numpy import ndarray


def configure_tensorflow_gpu() -> None:
    """
    Configura o TensorFlow para usar GPU quando disponível.

    - Se houver GPU, habilita memory growth para evitar que o TensorFlow
      aloque toda a memória da GPU logo no início.
    - Se não houver GPU, continua normalmente em CPU.
    """
    gpus = tf.config.list_physical_devices("GPU")

    if not gpus:
        print("[TensorFlow] Nenhuma GPU detectada. Usando CPU.")
        return

    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)

        logical_gpus = tf.config.list_logical_devices("GPU")

        print(f"[TensorFlow] GPUs físicas detectadas: {len(gpus)}")
        for idx, gpu in enumerate(gpus):
            print(f"[TensorFlow] GPU física {idx}: {gpu.name}")

        print(f"[TensorFlow] GPUs lógicas disponíveis: {len(logical_gpus)}")

    except RuntimeError as e:
        print(f"[TensorFlow] Aviso: não foi possível configurar memory growth: {e}")


configure_tensorflow_gpu()


def define_model():
    model = Sequential()
    model.add(
        Conv2D(
            32,
            (3, 3),
            activation="relu",
            kernel_initializer="he_uniform",
            input_shape=(28, 28, 1),
        )
    )
    model.add(MaxPool2D((2, 2)))
    model.add(Flatten())
    model.add(Dense(100, activation="relu", kernel_initializer="he_uniform"))
    model.add(Dense(10, activation="softmax"))

    opt = SGD(learning_rate=0.01, momentum=0.9)

    model.compile(
        optimizer=opt,
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )

    return model


class TrainerMINIST(FedClient):
    def __init__(self):
        super().__init__()
        self.model = define_model()
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None

    def prepare_data(self, path_to_data: str) -> DatasetInfo:
        csv_path = os.path.join(path_to_data, "dataset_subset.csv")

        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {csv_path}")

        df = pd.read_csv(csv_path)

        if "class" not in df.columns:
            raise ValueError(
                "A coluna target 'class' não foi encontrada em dataset_subset.csv"
            )

        X = df.drop(columns=["class"]).to_numpy(dtype=np.float32)
        y = df["class"].to_numpy(dtype=np.int32)

        if X.shape[1] != 784:
            raise ValueError(
                f"Esperado 784 features para MNIST, mas encontrado {X.shape[1]}"
            )

        X = X / 255.0
        X = X.reshape(-1, 28, 28, 1)

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y,
            shuffle=True,
        )

        y_train = to_categorical(y_train, num_classes=10)
        y_test = to_categorical(y_test, num_classes=10)

        self.X_train = X_train
        self.X_test = X_test
        self.y_train = y_train
        self.y_test = y_test

        print(
            f"[{self.get_client_id()}] Dados preparados: "
            f"X_train={self.X_train.shape}, X_test={self.X_test.shape}"
        )

        return DatasetInfo(
            client_id=self.get_client_id(),
            num_samples=self.X_train.shape[0],
        )

    def set_client_info(self, client_info: ClientInfo):
        return ClientInfo(self.get_client_id())

    def fit(self) -> bool:
        try:
            if tf.config.list_logical_devices("GPU"):
                device_name = "/GPU:0"
            else:
                device_name = "/CPU:0"

            print(f"[{self.get_client_id()}] Treinando em {device_name}")

            with tf.device(device_name):
                self.model.fit(
                    x=self.X_train,
                    y=self.y_train,
                    batch_size=64,
                    epochs=2,
                    verbose=2,
                )

            return True

        except Exception as e:
            print(f"Training failed in client {self.get_client_id()}: {e}")
            return False

    def evaluate(self) -> Metrics:
        if tf.config.list_logical_devices("GPU"):
            device_name = "/GPU:0"
        else:
            device_name = "/CPU:0"

        print(f"[{self.get_client_id()}] Avaliando em {device_name}")

        with tf.device(device_name):
            values = self.model.evaluate(
                x=self.X_test,
                y=self.y_test,
                verbose=False,
            )

            y_pred_probs = self.model.predict(
                self.X_test,
                verbose=0,
            )

        acc = float(values[1])

        y_true = np.argmax(self.y_test, axis=1)
        y_pred = np.argmax(y_pred_probs, axis=1)

        cm = confusion_matrix(y_true, y_pred, labels=list(range(10)))

        print(f"[{self.get_client_id()}] Accuracy local: {acc:.4f}")

        metrics = {
            MetricType.CONFUSION_MATRIX: cm.tolist(),
        }

        return Metrics(
            client_id=self.get_client_id(),
            metrics=metrics,
        )

    def update_weights(self, global_weights: list[ndarray]):
        self.model.set_weights(global_weights)

    def get_weights(self) -> list[ndarray]:
        return self.model.get_weights()