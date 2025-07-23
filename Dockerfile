FROM python:3.11-slim

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



# Inject env vars into global environment for cron, then start cron
CMD printenv >> /etc/environment && cron -f