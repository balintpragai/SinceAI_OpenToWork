# Part 1 data pipeline. The challenge package is NOT baked in: mount it read-only at /package.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    CCN_PACKAGE_ROOT=/package \
    CCN_LAKEHOUSE=/lakehouse \
    CCN_FILES_STAGING=/tmp/lakehouse_staging

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code plus the documents the index needs (GLOSSARY, ADRs, pipeline description).
COPY pipeline/ pipeline/
COPY tests/ tests/
COPY pytest.ini GLOSSARY.md ./
COPY docs/adr/ docs/adr/

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

RUN useradd --create-home ccn && mkdir -p /lakehouse && chown ccn /lakehouse
USER ccn

ENTRYPOINT ["python", "-m", "pipeline"]
CMD ["run"]
