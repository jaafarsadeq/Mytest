FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      chromium \
      ca-certificates \
      fonts-liberation \
      libasound2 libatk-bridge2.0-0 libatk1.0-0 libcairo2 libcups2 \
      libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libnspr4 libnss3 \
      libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 \
      libxext6 libxfixes3 libxkbcommon0 libxrandr2 \
      python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    NODE_ENV=production

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY src ./src

# Session DB + WA Web session persist here. Mount a volume on this path.
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 3037
CMD ["node", "src/bridge.js"]
