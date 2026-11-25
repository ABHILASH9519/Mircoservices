FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY relay/ relay/
RUN mkdir -p /data && chown 65534:65534 /data
USER 65534:65534
CMD ["python", "-m", "relay.api"]
