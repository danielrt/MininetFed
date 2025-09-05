#!/bin/bash

sudo docker build -t "mininetfed:broker" -f docker/Dockerfile.broker .
sudo docker build -t "mininetfed:auto_wait" -f docker/Dockerfile.auto_wait .
sudo docker build -t "mininetfed:auto_wait6" -f docker/Dockerfile.auto_wait6 .
sudo docker build -t "mininetfed:client" -f docker/Dockerfile.client .
sudo docker build -t "mininetfed:client_tf_cuda" -f docker/Dockerfile.client_tf_cuda .
sudo docker build -t "mininetfed:server" -f docker/Dockerfile.server .
sudo docker build -t "mininetfed:serversensor" -f docker/Dockerfile.serversensor .
sudo docker build -t "mininetfed:clientsensor" -f docker/Dockerfile.clientsensor .
