FROM --platform=linux/amd64 python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p config dbs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port for Streamlit
EXPOSE 8501

# Run both the monitor and UI
CMD ["sh", "-c", "python building_monitor.py & streamlit run ui.py --server.port=8501 --server.address=0.0.0.0"] 