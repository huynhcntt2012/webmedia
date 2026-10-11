FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libseccomp2 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 suni && useradd --uid 10001 --gid suni --create-home suni
RUN mkdir -p /var/lib/suni-media && chown suni:suni /var/lib/suni-media
COPY requirements.lock ./
RUN pip install -r requirements.lock
COPY --chown=suni:suni app ./app
COPY --chown=suni:suni alembic.ini ./
COPY --chown=suni:suni migrations ./migrations
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]

FROM base AS test
USER root
COPY requirements-test.lock ./
RUN pip install -r requirements-test.lock
COPY --chown=suni:suni tests ./tests
COPY --chown=suni:suni pyproject.toml ./
USER 10001:10001
CMD ["pytest", "-m", "integration", "-v", "-p", "no:cacheprovider"]
