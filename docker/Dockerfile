FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories and files
RUN mkdir -p src config dbs utils && \
    echo '{"use_proxy": true}' > config/proxy_config.json

# Copy the application files
COPY src/ ./src/

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port for Streamlit
EXPOSE 8501

# Run both the monitor and UI
CMD ["sh", "-c", "python src/building_monitor.py & streamlit run src/ui.py --server.port=8501 --server.address=0.0.0.0"] 