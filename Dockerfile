FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    mkvtoolnix \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install -e .

# Create directories
RUN mkdir -p /media /config /logs

VOLUME ["/media", "/config", "/logs"]

ENV SUBTAGGER_CONFIG=/config/config.yml
ENV SUBTAGGER_LOG_LEVEL=INFO

ENTRYPOINT ["subtagger"]
CMD ["--help"]
