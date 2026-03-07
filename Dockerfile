FROM python:3.12-slim-bookworm

# yt-dlp standalone binary
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 4040

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4040"]
