FROM node:22-alpine

WORKDIR /workspace/frontend

COPY frontend/package.json frontend/package-lock.json* ./

RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend /workspace/frontend

EXPOSE 5183

CMD ["sh", "-lc", "npm run dev -- --host 0.0.0.0 --port ${FRONTEND_PORT:-5183}"]
