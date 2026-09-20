FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

RUN mkdir -p /app/data /app/logs
VOLUME ["/app/data", "/app/logs"]

CMD ["python", "-m", "money_agent.daemon"]
