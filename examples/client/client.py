import importlib


import paho.mqtt.client as mqtt
import numpy as np

import json
import sys
import traceback
import time
import logging
from logging import Formatter
import os
try:
    import torch
except:
    pass

n_round = {}

def create_object(package, class_name, **atributtes):
    try:
        module = importlib.import_module(f"{package}")
        class_ = getattr(module, class_name)
        return class_(**atributtes)
    except (ModuleNotFoundError, AttributeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return None

os.umask(0o000)

n = len(sys.argv)

print(f"N: {n}", file=sys.stderr)

# check if client_instaciation_args are present
if n != 5 and n != 6:
    print(
        "correct use: python client.py <broker_address> <name> <id> <logs_path> [client_instanciation_args].")
    exit()

BROKER_ADDR = sys.argv[1]
CLIENT_NAME = sys.argv[2]
CLIENT_ID = int(sys.argv[3])
log_file = f'{sys.argv[4]}/{CLIENT_NAME}.log'
spnfl_log_file = f'{sys.argv[4]}/{CLIENT_NAME}_spn.log'
# MODE = sys.argv[4]
CLIENT_INSTANTIATION_ARGS = {}
if len(sys.argv) == 6 and (sys.argv[5] is not None):
    CLIENT_INSTANTIATION_ARGS = json.loads(sys.argv[5])

print(f"log_file: {log_file}", file=sys.stderr)

trainer_class = CLIENT_INSTANTIATION_ARGS.get("trainer_class")
if trainer_class is None:
    trainer_class = "TrainerMNIST"

selected = False

FORMAT = "%(asctime)s - %(infotype)-6s - %(levelname)s - %(message)s"
# logging.basicConfig(level=logging.INFO, filename=log_file,
#                    format=FORMAT, filemode="w")
# logger = logging.getLogger(__name__)

# logger geral
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
h_general = logging.FileHandler(filename=log_file, mode="w")
h_general.setFormatter(Formatter(FORMAT))
logger.addHandler(h_general)

# logger spnfl (artigo https://sol.sbc.org.br/index.php/sbrc/article/view/35122/34913)
FORMAT_SPNFL = "%(asctime)s - %(message)s"
spnfl_logger = logging.getLogger("spnfl")
spnfl_logger.setLevel(logging.INFO)
spnfl_logger.propagate = False  # não manda para os handlers do "myapp"
h_spnfl = logging.FileHandler(spnfl_log_file, mode="w")
h_spnfl.setFormatter(Formatter(FORMAT_SPNFL))
spnfl_logger.addHandler(h_spnfl)


def default(obj):
    if type(obj).__module__ == np.__name__:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj.item()
    elif type(obj).__module__ == torch.__name__:
        if isinstance(obj, torch.Tensor):
            return obj.tolist()
    else:
        try:
            from Pyfhel import PyCtxt
            if isinstance(obj, PyCtxt):
                return obj.to_bytes().decode('cp437')
        except:
            pass
    raise TypeError('Tipo não pode ser serializado:', type(obj))


def has_method(o, name):
    return callable(getattr(o, name, None))


class color:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD_START = '\033[1m'
    BOLD_END = '\033[0m'
    RESET = "\x1B[0m"


# subscribe to queues on connection
def on_connect(client, userdata, flags, rc):
    subscribe_queues = ['minifed/selectionQueue',
                        'minifed/posAggQueue', 'minifed/stopQueue', 'minifed/serverArgs']
    for s in subscribe_queues:
        client.subscribe(s)


# callback for serverArgs: update the args with new information send by the server, between the round 0 and the round 1.
def on_server_args(client, userdata, message):
    msg = json.loads(message.payload.decode("utf-8"))
    if msg['id'] == CLIENT_NAME:
        if msg['args'] is not None:
            trainer.set_args(msg['args'])

        client.publish('minifed/ready',
                       json.dumps({"id": CLIENT_NAME}, default=default))


"""
callback for selectionQueue: the selection queue is sent by the server; 
the client checks if it's selected for the current round or not. If yes, 
the client trains and send the training results back.
"""
def on_message_selection(client, userdata, message):
    global selected
    global n_round
    msg = json.loads(message.payload.decode("utf-8"))
    if msg['id'] == CLIENT_NAME:
        client_id = msg['id']
        if client_id not in n_round:
            n_round[client_id] = 0
        n_round[client_id] += 1
        spnfl_logger.info(f'START_ROUND {n_round[client_id]}')
        if bool(msg['selected']):
            spnfl_logger.info(f'T_SELECT True')
            selected = True
            print(color.BOLD_START + '[{}] new round starting'.format(n_round[client_id]) + color.BOLD_END)
            print(
                f'trainer was selected for training this round and will start training!')

            resp_dict = {'id': CLIENT_NAME, 'success': True }
            t0 = time.time()
            try:
                trainer.train_model()
                resp_dict['weights'] = trainer.get_weights()
                resp_dict['num_samples'] = trainer.get_num_samples()
                if has_method(trainer, 'get_training_args'):
                    resp_dict['training_args'] = trainer.get_training_args()
            except Exception:
                print(traceback.format_exc())
                resp_dict['success'] = False
            t_train = time.time() - t0

            spnfl_logger.info(f"T_TRAIN {resp_dict['success']} {t_train}")
            response = json.dumps(resp_dict, default=default)

            client.publish('minifed/preAggQueue', response)
            spnfl_logger.info(f'T_RETURN_0')
            print(f'finished training and sent weights!')
        else:
            spnfl_logger.info(f'T_SELECT False')
            selected = False
            print(color.BOLD_START + '[{}] new round starting'.format(n_round[client_id]) + color.BOLD_END)
            print(f'trainer was not selected for training this round')


# callback for posAggQueue: gets aggregated weights and publish validation results on the metricsQueue
def on_message_agg(client, userdata, message):
    global selected
    spnfl_logger.info(f'T_SEND')
    print(f'received aggregated weights!')
    msg = json.loads(message.payload.decode("utf-8"))
    agg_weights = [np.asarray(w, dtype=np.float32)
                   for w in msg["agg_response"][CLIENT_NAME]["weights"]]
    results = trainer.all_metrics()
    results['selected'] = selected
    response = json.dumps(
        {'id': CLIENT_NAME, "metrics": results}, default=default)
    trainer.update_weights(agg_weights)

    if has_method(trainer, "agg_response_extra_info"):
        trainer.agg_response_extra_info(
            msg["agg_response"][CLIENT_NAME] | msg["agg_response"]['all'])

    print(f'sending eval metrics!\n')
    client.publish('minifed/metricsQueue', response)
    spnfl_logger.info(f'T_RETURN_1')
    spnfl_logger.info(f'END_ROUND {n_round[CLIENT_NAME]}')


# callback for stopQueue: if conditions are met, stop training and exit process
def on_message_stop(client, userdata, message):
    print(color.RED + f'received message to stop!')
    trainer.set_stop_true()
    exit()

trainer = create_object("trainer", trainer_class, id=CLIENT_ID,
                        name=CLIENT_NAME, args=CLIENT_INSTANTIATION_ARGS)
client = mqtt.Client(str(CLIENT_NAME))
client.connect(BROKER_ADDR, keepalive=0)
client.on_connect = on_connect
client.message_callback_add('minifed/selectionQueue', on_message_selection)
client.message_callback_add('minifed/posAggQueue', on_message_agg)
client.message_callback_add('minifed/stopQueue', on_message_stop)
client.message_callback_add('minifed/serverArgs', on_server_args)

# start waiting for jobs
client.loop_start()

spnfl_logger.info("INIT_EXPERIMENT")

response = json.dumps({'id': CLIENT_NAME, 'accuracy': trainer.eval_model(
), "metrics": trainer.all_metrics()}, default=default)
client.publish('minifed/registerQueue',  response)
spnfl_logger.info(f'T_ARRIVAL')
print(color.BOLD_START +
      f'trainer {CLIENT_NAME} connected!\n' + color.BOLD_END)


while not trainer.get_stop_flag():
    time.sleep(1)

client.loop_stop()
