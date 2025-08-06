FROM python:3.11-slim

VOLUME /app/plots

# Set working directory
WORKDIR /app

# Install cron
RUN apt-get update && apt-get install -y cron && \
    apt-get clean

# Install any needed Python packages
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Install crontab file
COPY crontab.txt /app/crontab.txt
RUN crontab /app/crontab.txt

# Copy files
COPY main.py /app/main.py
COPY envLogos.py /app/envLogos.py 

# Expose port for HTTP access
EXPOSE 8000

# Inject env vars into global environment, then start both cron and HTTP server in foreground
CMD printenv >> /etc/environment && \
    cron && \
    python3 -m http.server 8000 --directory /app/plots