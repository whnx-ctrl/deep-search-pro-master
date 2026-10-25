FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get -o Acquire::Retries=5 update \
    && for attempt in 1 2 3 4 5; do \
        apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
            build-essential \
            libffi-dev \
            libcairo2-dev \
            libfreetype6-dev \
            libjpeg62-turbo-dev \
            libopenjp2-7-dev \
            pkg-config \
            zlib1g-dev \
        && break; \
        if [ "$attempt" -eq 5 ]; then exit 1; fi; \
        sleep 3; \
    done \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip wheel --wheel-dir /wheels --requirement requirements.txt

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get -o Acquire::Retries=5 update \
    && for attempt in 1 2 3 4 5; do \
        apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
            ca-certificates \
            fonts-noto-cjk \
            libcairo2 \
            libffi8 \
            libfontconfig1 \
            libharfbuzz-subset0 \
            libjpeg62-turbo \
            libopenjp2-7 \
            libpango-1.0-0 \
            libpangoft2-1.0-0 \
            shared-mime-info \
        && break; \
        if [ "$attempt" -eq 5 ]; then exit 1; fi; \
        sleep 3; \
    done \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels --requirement /tmp/requirements.txt \
    && rm -rf /wheels /tmp/requirements.txt \
    && python -m weasyprint --info

RUN groupadd --system app \
    && useradd --system --gid app --create-home app

COPY --chown=app:app . /app
RUN mkdir -p /app/data /app/logs /app/output /app/updated \
    && chown -R app:app /app/data /app/logs /app/output /app/updated

USER app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
