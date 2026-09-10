FROM python:3.12-slim
WORKDIR /workspace
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
COPY backend /workspace/backend
RUN useradd --create-home queuesense
USER queuesense
CMD ["uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001", "--no-proxy-headers"]
