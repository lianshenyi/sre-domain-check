FROM node:18-alpine AS frontend-build
WORKDIR /build/frontend
COPY domain-admin-web/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY domain-admin-web/ ./
ARG VITE_APP_API=/api
ARG VITE_BASE_URL=/
RUN printf "NODE_ENV=production\nVITE_APP_API=%s\nVITE_BASE_URL=%s\n" "$VITE_APP_API" "$VITE_BASE_URL" > .env.production \
    && npm run build

FROM python:3.7.17-slim-bullseye
WORKDIR /app/backend
COPY domain-admin/ /app/backend/
COPY --from=frontend-build /build/frontend/dist /srv/frontend
COPY docker/start-app.py /usr/local/bin/start-app.py

RUN pip install --no-cache-dir --upgrade pip setuptools wheel gunicorn \
    && pip install --no-cache-dir -r requirements/production.txt

EXPOSE 8000
CMD ["python", "/usr/local/bin/start-app.py"]
