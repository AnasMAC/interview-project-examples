FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    DJANGO_SETTINGS_MODULE=atlas.settings.dev

WORKDIR /app

# Dependencies first so source edits keep the pip layer cached.
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt && pip check

# Compose bind-mounts the source over /app; the copy keeps the image usable alone.
COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
