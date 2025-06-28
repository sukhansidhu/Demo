# Use official Python image
FROM python:3.11-slim-bullseye

# Install system dependencies with non-free repository
RUN echo "deb http://deb.debian.org/debian bullseye non-free" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y \
    unrar \
    p7zip-full \
    ffmpeg \
    rar \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

# Create temp directory
RUN mkdir -p /tmp/archive_bot

# Start the bot
CMD ["python", "main.py"]
