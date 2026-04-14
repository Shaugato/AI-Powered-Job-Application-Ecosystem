FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential curl git nodejs npm chromium tesseract-ocr \
     fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libcairo2 libcups2 libdbus-1-3 libdrm2 \
     libgbm1 libgtk-3-0 libnspr4 libnss3 libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 libxrandr2 xdg-utils \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY pyproject.toml README.md /workspace/
COPY backend /workspace/backend
COPY infra/renderer /workspace/infra/renderer

RUN cd /workspace/infra/renderer \
  && npm install

RUN pip install --upgrade pip \
  && pip install -e .[dev] \
  && python -m playwright install chromium

EXPOSE 8000

