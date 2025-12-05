class ServerOptions:
    MIN_CLIENTS = "min_clients"
    STOP_VALUE = "stop_value"
    EARLY_STOP_VALUE = "early_stop_value"
    NUM_ROUNDS = "num_rounds"
    METRIC = "metric"
    MODEL_AGGREGATOR = "model_aggregator"
    CLIENT_SELECTOR = "client_selector"
    CLIENT_ACCEPTOR = "client_acceptor"

class MetricType:
    ACCURACY = "accuracy"

class ClientSelectorType:
    ALL_CLIENTS = "all_clients"

class ClientAcceptorType:
    ALL_CLIENTS = "all_clients"

class AggregatorType:
    FED_AVG = "fed_avg"