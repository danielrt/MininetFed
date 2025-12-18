import os
import numpy as np
from keras.src.utils import to_categorical
from mininetfed.core.dto.client_info import ClientInfo
from mininetfed.core.dto.dataset_info import DatasetInfo
from mininetfed.core.dto.metrics import Metrics
from mininetfed.core.fed_options import MetricType
from mininetfed.core.nodes.fed_client import FedClient
from numpy import ndarray
from sklearn.model_selection import train_test_split

from tensorflow.keras.layers import Conv2D, MaxPool2D, Flatten, Dense
from tensorflow.keras.optimizers import SGD
from tensorflow.keras.models import Sequential

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def define_model():
    model = Sequential()
    model.add(Conv2D(32, (3, 3), activation='relu',
                     kernel_initializer='he_uniform', input_shape=(28, 28, 1)))
    model.add(MaxPool2D((2, 2)))
    model.add(Flatten())
    model.add(Dense(100, activation='relu',
                    kernel_initializer='he_uniform'))
    model.add(Dense(10, activation='softmax'))
    opt = SGD(learning_rate=0.01, momentum=0.9)
    model.compile(
        optimizer=opt, loss='categorical_crossentropy', metrics=['accuracy'])
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
        # Carregar arquivo .npz
        data = np.load(path_to_data + "/mnist_iid_N4_subset.npz")
        X = data["X"].astype("float32") / 255.0
        y = data["y"].astype("int32")

        # Adicionar canal (necessário para CNNs)
        X = X[..., None]  # (N, 28, 28, 1)

        # Fazer o split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=0.2,
            random_state=42,
            stratify=y,  # mantém distribuição das classes
            shuffle=True
        )

        y_train = to_categorical(y_train, num_classes=10)
        y_test = to_categorical(y_test, num_classes=10)

        self.X_train, self.X_test = X_train, X_test
        self.y_train, self.y_test = y_train, y_test

        return DatasetInfo(client_id=self.get_client_id(), num_samples=self.X_train.shape[0])


    def set_client_info(self, client_info: ClientInfo):
        return ClientInfo(self.get_client_id())

    def fit(self) -> bool:
        try:
            self.model.fit(x=self.X_train, y=self.y_train, batch_size=64, epochs=10, verbose=3)
            return True
        except Exception as e:
            print(f"Training failed in client {self.get_client_id()}: {e}")
            return False

    def evaluate(self) -> Metrics:
        values = self.model.evaluate(x=self.X_test, y=self.y_test, verbose=False)
        metrics = {MetricType.ACCURACY : values[1]}
        return Metrics(client_id=self.get_client_id(), metrics=metrics)

    def update_weights(self, global_weights: list[ndarray]):
        self.model.set_weights(global_weights)

    def get_weights(self) -> list[ndarray]:
        return self.model.get_weights()


