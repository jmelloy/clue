# ---- Stage 1: Build frontend assets ----
FROM node:22-alpine AS frontend-build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ .
RUN npm run build -- --outDir /assets

# ---- Stage 2: Python backend + static assets ----
FROM python:3.12-slim

WORKDIR /app

COPY backend/pyproject.toml .
RUN pip install --no-cache-dir .

COPY backend/ .

# Copy frontend build output into the static directory
COPY --from=frontend-build /assets ./static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
