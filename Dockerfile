FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_BASE_URL=/api VITE_DEMO_MODE=true
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    APP_ENV=production FINFLOW_DEMO_MODE=true FINFLOW_SERVE_FRONTEND=true
WORKDIR /app
COPY backend/requirements.lock backend/requirements.lock
RUN python -m pip install --no-cache-dir -r backend/requirements.lock \
    && useradd --create-home appuser
COPY backend/ backend/
COPY --from=frontend /build/dist frontend/dist
USER appuser
EXPOSE 8000
CMD ["python", "backend/run_prod.py"]
