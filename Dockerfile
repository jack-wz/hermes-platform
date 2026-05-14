FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose dashboard port
EXPOSE 5002

# Start dashboard
CMD ["python3", "build/workspace/hermes-dashboard.py"]
