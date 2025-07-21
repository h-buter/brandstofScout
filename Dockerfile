FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy files
COPY main.py /app/main.py
#For logo info
COPY envLogos.py /app/envLogos.py 
COPY crontab.txt /app/crontab.txt
COPY requirements.txt /app/requirements.txt

# Install cron
RUN apt-get update && apt-get install -y cron && \
    apt-get clean

# Install any needed Python packages (optional)
RUN pip install -r requirements.txt

# Install crontab file
RUN crontab /app/crontab.txt

# Inject env vars into global environment for cron, then start cron
CMD printenv >> /etc/environment && cron -f