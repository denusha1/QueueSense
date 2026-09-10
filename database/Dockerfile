FROM python:3.12-slim
WORKDIR /workspace
COPY database/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY database /workspace/database
COPY data/generator /workspace/data/generator
ENTRYPOINT ["python", "database/scripts/manage.py"]
