FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 \
        libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
        libcairo2 libasound2t64 libatspi2.0-0t64 libxshmfence1 \
        fonts-liberation fonts-noto-color-emoji && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY . .

EXPOSE 4040

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4040"]
