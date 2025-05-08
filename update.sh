#!/bin/bash

# Exit on any error
set -e

# Configuration
UNRAID_IP="your-unraid-ip"  # Replace with your Unraid server IP

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Updating Building Monitor ===${NC}"

# Build new version
echo -e "${BLUE}Building new version...${NC}"
./build.sh

# Copy docker-compose.yml to Unraid
echo -e "${BLUE}Copying docker-compose.yml to Unraid...${NC}"
scp docker-compose.yml root@${UNRAID_IP}:/mnt/user/appdata/building-monitor/

# Update container on Unraid
echo -e "${BLUE}Updating container on Unraid...${NC}"
ssh root@${UNRAID_IP} "cd /mnt/user/appdata/building-monitor && docker-compose pull && docker-compose up -d"

echo -e "${GREEN}Update complete!${NC}"
echo -e "The new version is now running on your Unraid server."
echo -e "You can access the UI at: http://${UNRAID_IP}:8501" 