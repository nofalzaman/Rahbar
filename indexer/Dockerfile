FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY indexer/requirements.txt .
RUN pip install -r requirements.txt

COPY indexer/pipeline ./pipeline

ARG CORPUS_SRC=eval/fixtures
COPY ${CORPUS_SRC} /corpus

RUN useradd --system --uid 10001 --no-create-home rahbar
USER 10001

ENTRYPOINT ["python", "-m", "pipeline.run"]