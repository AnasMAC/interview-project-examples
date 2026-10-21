FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# Dependencies first so source edits keep the pip layer cached.
COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=1
RUN if [ "$INSTALL_DEV" = "1" ]; then pip install -r requirements-dev.txt; \
    else pip install -r requirements.txt; fi \
    && pip check

# Compose bind-mounts the source over /app; the copy keeps the image usable alone.
COPY . .

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "gatekeeper.core.app:create_app()"]
