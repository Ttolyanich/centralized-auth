FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Environment variables defaults
ENV PORT=5001
ENV BIND_HOST=0.0.0.0
ENV DATABASE_PATH=/app/data/users.db
ENV OPENVPN_WEB_CONFIG=/app/data/config.json

# Expose the default port
EXPOSE 5001

# Run the application
CMD ["python", "app.py"]
