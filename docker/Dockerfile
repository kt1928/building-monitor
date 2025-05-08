FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files
COPY src/ ./src/
COPY config/ ./config/
COPY utils/ ./utils/

# Create necessary directories
RUN mkdir -p config dbs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Create default proxy config
RUN echo '{"use_proxy": true}' > config/proxy_config.json

# Expose port for Streamlit
EXPOSE 8501

# Run both the monitor and UI
CMD ["sh", "-c", "python src/building_monitor.py & streamlit run src/ui.py --server.port=8501 --server.address=0.0.0.0"] 