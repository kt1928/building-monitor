#!/bin/bash

# Configuration
UNRAID_IP="your-unraid-ip"  # Replace with your Unraid server IP
DOCKER_USERNAME="kappy1928"
IMAGE_NAME="building-monitor"
CHECK_INTERVAL=3600  # Check every hour

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to get current image digest
get_current_digest() {
    ssh root@${UNRAID_IP} "docker inspect ${DOCKER_USERNAME}/${IMAGE_NAME}:latest --format='{{.RepoDigests}}'"
}

# Function to get latest image digest
get_latest_digest() {
    docker manifest inspect ${DOCKER_USERNAME}/${IMAGE_NAME}:latest --format='{{.Descriptor.digest}}'
}

# Function to update container
update_container() {
    echo -e "${BLUE}New version available. Updating...${NC}"
    ssh root@${UNRAID_IP} "cd /mnt/user/appdata/building-monitor && docker-compose pull && docker-compose up -d"
    echo -e "${GREEN}Update complete!${NC}"
}

# Main loop
echo -e "${BLUE}Starting Building Monitor updater...${NC}"
echo -e "Checking for updates every ${CHECK_INTERVAL} seconds"
echo -e "Press Ctrl+C to stop"

while true; do
    current_digest=$(get_current_digest)
    latest_digest=$(get_latest_digest)
    
    if [ "$current_digest" != "$latest_digest" ]; then
        update_container
    else
        echo -e "${GREEN}No updates available${NC}"
    fi
    
    sleep ${CHECK_INTERVAL}
done 