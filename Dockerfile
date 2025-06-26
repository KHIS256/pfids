# Step 1: Start with a lightweight official Python base image.
FROM python:3.11-slim

# Step 2: Set environment variables to prevent installers from asking questions.
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Step 3: Update the system's package list and install Google Chrome.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates fonts-wqy-zenhei \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update && apt-get install -y --no-install-recommends \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Step 4: Set the working directory inside the container.
WORKDIR /app

# Step 5: Copy and install Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 6: Copy the rest of your application code into the container.
COPY . .

# Step 7: Define the command to run your application.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "2", "app:app"]