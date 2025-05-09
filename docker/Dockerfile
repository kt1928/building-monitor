FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p src config dbs utils

# Copy the application files
COPY src/ ./src/

# Create empty config directory structure
RUN mkdir -p config && \
    touch config/addresses.txt && \
    touch config/webhook.txt && \
    touch config/schedule.json && \
    touch config/proxy.txt

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Create volume for persistent data
VOLUME ["/app/config", "/app/dbs"]

# Expose port for Streamlit
EXPOSE 8504

# Run the UI only
CMD ["streamlit", "run", "src/ui.py", "--server.port=8504", "--server.address=0.0.0.0"] 