# Calma: one container that builds the React app and serves it from the FastAPI backend.

# 1) Build the web app
FROM node:24-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2) Python API + built web app
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY data/demo_pages ./data/demo_pages
COPY --from=web /app/frontend/dist ./frontend/dist
# Render sets $PORT. Demo data is created on first start (see CALMA_SEED_IF_EMPTY).
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
