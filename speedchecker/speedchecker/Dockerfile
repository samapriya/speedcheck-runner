FROM python:3.10-slim

# Install necessary packages including chromium for Playwright
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

# Create directories for static web files and data
RUN mkdir -p /app/static /app/data

# Copy the HTML/JS interface
COPY static/index.html /app/static/

# Create the Flask application
COPY app.py /app/

# Expose the port
EXPOSE 3667

# Run the Flask application
CMD ["python", "app.py"]
