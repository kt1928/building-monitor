#!/bin/bash

# Exit on any error
set -e

# Configuration
DOCKER_USERNAME="kappy1928"  # Docker Hub username
IMAGE_NAME="building-monitor"
VERSION=$(date +%Y%m%d_%H%M%S)  # Creates a version based on timestamp

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Building Building Monitor Docker Image ===${NC}"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running"
    exit 1
fi

# Check if logged in to Docker Hub
if ! docker info | grep -q "Username"; then
    echo "Please login to Docker Hub first:"
    docker login
fi

echo -e "${BLUE}Building image...${NC}"
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 \
    -t ${DOCKER_USERNAME}/${IMAGE_NAME}:latest \
    -t ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION} \
    --push .

echo -e "${GREEN}Successfully built and pushed:${NC}"
echo -e "Latest: ${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
echo -e "Version: ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"

# Update docker-compose.yml with the new version
sed -i.bak "s|image: ${DOCKER_USERNAME}/${IMAGE_NAME}:.*|image: ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}|" docker-compose.yml
rm docker-compose.yml.bak

echo -e "${GREEN}Updated docker-compose.yml with new version${NC}"
echo -e "${BLUE}To deploy on Unraid:${NC}"
echo "1. Copy the new docker-compose.yml to your Unraid server"
echo "2. Run: docker-compose pull && docker-compose up -d" 