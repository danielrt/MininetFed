# MininetFed

MininetFed is a federated learning environment emulation tool based on Mininet and Containernet.

Its main features include:

- **Addition of new Mininet nodes**: Server, Client. These containerized nodes allow configuration of connection characteristics, available RAM, CPU, etc.
- **Automatic setup of a communication environment using MQTT**
- **Facilitates the implementation of new aggregation and client selection functions**
- **Enables the development of new trainers** to be executed on the clients (model + dataset + manipulations).
- **Easy to develop**: User just need to define the trainer (client) code and topology of the net.


# Mailing List  
[https://groups.google.com/forum/#!forum/mininetfed-discuss](https://groups.google.com/g/mininetfed-discuss)

# Getting Started with MininetFed


### Cloning the MininetFed Repository:

```
git clone -b refactor --single-branch https://github.com/danielrt/mininetfed.git

```

## Prerequisites

### Installing ContainerNet

MininetFed requires ContainerNet. Before installing it, install its dependencies using the following command:

```
sudo apt install ansible git aptitude
```

#### Tested ContainerNet Version (Recommended)

The recommended version for full MininetFed functionality can be found in the following repository:

```
git clone https://github.com/ramonfontes/containernet.git
cd containernet
sudo util/install.sh -W
```

### Compiling and Installing MininetFed

```bash
cd ../MininetFed
sudo python setup.py install
```

## Running the First Example

A basic example can be executed to test MininetFed's functionality:

```bash
pip install sckit-learn pandas

cd examples/basic/

python3 mnist_gen_clients.py -N 4 --mode iid --py_src_dir ./client_code

sudo python basic.py
```
The basic example simulates a federated training using the MNIST dataset, with four clients (each one with it's 
own data and code) and a server. It consists of the following:

- **basic.py**: this script defines the MininetFed topology. It defines the FL parameters, creates a switch, a broker, 
a server and four clients. Then, it runs the training until a stop condition is achieved.
- **client_code/mnist_trainer.py**: the trainer (client) code that each MininetFed host will run.
- **client_requirements.txt**: the package requirements for the trainer. In this example, we use TensorFlow to define 
and train the model and Scikit-learn to load and prepare the data.
- **mnist_gen_clients.py**: a helper script created just for this example (**NOT PART OF MININETFED**). 
It downloads the MNIST dataset, divides it into four new datasets with the same original's distribution. Then 
it creates a path for each client containing the client code and the corresponding data.

After running the command *mnist_gen_clients.py* four folders are created:

- **clients/client0**: code and dataset for client0.
- **clients/client1**: code and dataset for client1.
- **clients/client2**: code and dataset for client2.
- **clients/client3**: code and dataset for client3.

These folders represents the space each client is allowed to read or save data. In this example, we use the 
*mnist_gen_clients.py* script to automate the creation of these folders.

After running *basic.py*, the mininetfed topology is created and the federated training starts. You should see 
a xterm terminal for the server, broker and each client: 

<img src="https://github.com/danielrt/MininetFed/blob/refactor/imgs/basic_example_exe.png" alt="screenshot of basic example training execution" />

The server and broker create their own folder if not specified. Each node will generate logs in it's own folders:

<img src="https://github.com/danielrt/MininetFed/blob/refactor/imgs/basic_example_folders.png" alt="screenshot of experiment folder" />

After execution ends, all windows will close automatically. The results can be checked in the server folder.

# Documentation

https://github.com/lprm-ufes/MininetFed/tree/development/docs

# How to Cite

If you use MininetFed in your research or work, please cite the following paper:

```
@inproceedings{sarmento2024mininetfed,  
  title={MininetFed: A tool for assessing client selection, aggregation, and security in Federated Learning},  
  author={Sarmento, Eduardo MM and Bastos, Johann JS and Villaca, Rodolfo S and Comarela, Giovanni and Mota, Vin{\'\i}cius FS},  
  booktitle={2024 IEEE 10th World Forum on Internet of Things (WF-IoT)},  
  pages={1--6},  
  year={2024},  
  organization={IEEE}  
}  
```

# Papers that Used MininetFed

See the complete list of citations [here](docs/en/citations.md).

# Development Team

[Eduardo Sarmento](https://github.com/eduardo-sarmento)  
[Johann Jakob Bastos](https://github.com/jjakob10)  
[João Pedro Batista](https://github.com/joaoBatista04)  
[Ramon Fontes](https://github.com/ramonfontes)  
[Rodolfo Villaça](https://github.com/rodolfovillaca)  
[Vinícius Mota](https://github.com/vfsmota)
[Daniel Ribeiro Trindade](https://github.com/danielrt)

