FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir httpx==0.28.1 && useradd --system --uid 10001 rahbar
COPY eval/ragops_suite.py ./eval/ragops_suite.py
COPY eval/*.jsonl ./eval/
COPY eval/paraphrases.json ./eval/paraphrases.json
COPY ragops ./ragops
USER 10001
ENTRYPOINT ["python", "-m", "eval.ragops_suite"]
