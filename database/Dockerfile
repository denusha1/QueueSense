FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY database/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --timeout 60 --retries 6 -r /tmp/requirements.txt
COPY database /workspace/database
COPY data/generator /workspace/data/generator
RUN useradd --create-home --uid 10001 --user-group queuesense
USER 10001
ENTRYPOINT ["python", "database/scripts/manage.py"]
