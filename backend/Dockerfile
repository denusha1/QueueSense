FROM python:3.12-slim AS dependencies
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
COPY backend/requirements.lock /tmp/requirements.lock
RUN /opt/venv/bin/pip install --no-cache-dir --timeout 60 --retries 6 -r /tmp/requirements.lock

FROM python:3.12-slim AS runtime
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY --from=dependencies /opt/venv /opt/venv
COPY backend /workspace/backend
COPY ml /workspace/ml
RUN useradd --create-home --uid 10001 --user-group queuesense
USER 10001
EXPOSE 8001
CMD ["uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001", "--no-proxy-headers", "--no-access-log"]
