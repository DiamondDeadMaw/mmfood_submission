#!/bin/bash

IMAGE_NAME="hitl-val"
CONTAINER_NAME="hitl-val"

echo "Building"
docker build -t $IMAGE_NAME .
echo "Stopping old containers"
docker rm -f $CONTAINER_NAME 2>/dev/null || true

echo "Running new container"
docker run -d --add-host=host.docker.internal:host-gateway --rm \
--name $CONTAINER_NAME \
-p 7301:7301 \
$IMAGE_NAME

echo "Container running"
