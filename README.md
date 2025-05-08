# Building Monitor

A Docker-based application that monitors building statuses and sends notifications via Discord.

## Features

- Monitors building statuses at scheduled intervals
- Sends notifications via Discord
- Web UI for configuration
- Automatic updates through Docker
- Automated builds and deployments via GitHub Actions

## Setup

1. Create a Docker Hub account
2. Set up GitHub repository secrets:
   - `DOCKER_USERNAME`: Your Docker Hub username
   - `DOCKER_PASSWORD`: Your Docker Hub password
3. The application is organized in the following directory structure:
   - `src/`: Source code for the application
   - `config/`: Configuration files
   - `docker/`: Docker-related files

## Development

1. Make changes to the code
2. Push to GitHub:
   ```bash
   git add .
   git commit -m "Your changes"
   git push
   ```
3. GitHub Actions will automatically build and push to Docker Hub
4. Update the container in Unraid

## Configuration

The application uses the following configuration files in the `config` directory:
- `addresses.txt`: List of addresses to monitor
- `webhook.txt`: Discord webhook URL

## Accessing the UI

The web UI is available at:
```
http://your-unraid-ip:8501
```