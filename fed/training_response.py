from numpy import ndarray

class TrainingResponse:
    def __init__(self, success : bool, weights : list[ndarray], num_samples : int, **training_args):
        self.success = success
        self.weights = weights
        self.num_samples = num_samples
        self.training_args = training_args

    def get_success(self):
        return self.success

    def get_weights(self):
        return self.weights

    def get_num_samples(self):
        return self.num_samples

    def get_training_args(self):
        return self.training_args
