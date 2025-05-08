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
COPY config/ ./config/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Create default proxy config
RUN echo "http://customer-kappy_nrNdL-cc-US:3tGCOHQaFsfv1pzlrDAm+@pr.oxylabs.io:7777" > config/proxy.txt

# Create volume for persistent data
VOLUME ["/app/config", "/app/dbs"]

# Expose port for Streamlit
EXPOSE 8501

# Run both the monitor and UI
CMD ["sh", "-c", "python src/building_monitor.py & streamlit run src/ui.py --server.port=8501 --server.address=0.0.0.0"] 