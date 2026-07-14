# SKINRUSH — Django backend (server-rendered site), deployed on Fly.io.
# The whole repo goes into the image because Django serves the static assets
# (styles.css, ssr.css, images/, ...) from the repo root.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python deps first so this layer is cached between code changes.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Copy the rest of the project (front-end at root + Django in backend/).
COPY . .

# Collect Django's own static files (admin, DRF) — served by WhiteNoise.
WORKDIR /app/backend
RUN python manage.py collectstatic --noinput

EXPOSE 8080

# On each start: apply migrations, seed data, ensure the admin user,
# then run the production server.
CMD ["sh", "-c", "python manage.py migrate && python manage.py seed && python manage.py ensure_admin && gunicorn skinrush.wsgi:application --bind 0.0.0.0:8080"]
