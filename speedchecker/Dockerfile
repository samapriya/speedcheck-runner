FROM python:3.10-slim
# Install necessary packages including chromium for Playwright and cron
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    wget \
    xdg-utils \
    cron \
    && rm -rf /var/lib/apt/lists/*
# Install Playwright
RUN pip install playwright
RUN playwright install chromium
# Install Flask and other required dependencies
RUN pip install flask pandas pyarrow schedule requests urllib3
# Create app directory
WORKDIR /app
# Copy Python scripts
COPY speedtest_openspeedtest.py /app/
COPY speedtest_speedsmart.py /app/
COPY scheduled_tests.py /app/
RUN chmod +x /app/scheduled_tests.py
# Create directories for static web files and data
RUN mkdir -p /app/static /app/data
# Copy the HTML/JS interface
COPY static/index.html /app/static/
# Create the Flask application
COPY app.py /app/
# Setup cron job to run scheduler every minute
RUN echo "*/5 * * * * /usr/local/bin/python /app/scheduled_tests.py >> /app/data/cron.log 2>&1" > /etc/cron.d/speedtest-cron
RUN chmod 0644 /etc/cron.d/speedtest-cron
RUN crontab /etc/cron.d/speedtest-cron
# Create startup script to run both Flask app and cron
RUN echo '#!/bin/bash\nservice cron start\npython /app/app.py' > /app/start.sh
RUN chmod +x /app/start.sh
# Expose the port
EXPOSE 3667
# Run both the Flask application and cron
CMD ["/app/start.sh"]
