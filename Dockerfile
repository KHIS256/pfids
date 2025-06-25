# Step 1: Start with a lightweight official Python base image.
# This gives us a clean Linux environment with Python 3.11 pre-installed.
FROM python:3.11-slim

# Step 2: Set environment variables to prevent installers from asking questions.
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Step 3: Update the system's package list and install Google Chrome.
# This is the core logic that failed in the build command. Here, it's clean and reliable.
# We also install fonts to prevent text rendering issues in headless mode.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    fonts-wqy-zenhei \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update && apt-get install -y --no-install-recommends \
    google-chrome-stable \
    # Clean up the package cache to make our final image smaller.
    && rm -rf /var/lib/apt/lists/*

# Step 4: Set the working directory inside the container.
WORKDIR /app

# Step 5: Copy and install Python dependencies.
# We copy requirements.txt first to take advantage of Docker's layer caching.
# This makes future builds faster if the requirements haven't changed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 6: Copy the rest of your application code into the container.
COPY . .

# Step 7: Define the command to run your application.
# This tells Render how to start your Gunicorn server.
# Render services listen on port 10000.
# Use only one worker to conserve memory on the free plan
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--timeout", "120", "app:app"]