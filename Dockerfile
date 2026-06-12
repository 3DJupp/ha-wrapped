FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wrapped.py template.html ./
# /data holds config.yaml and receives the rendered HTML
WORKDIR /data
ENTRYPOINT ["python3", "/app/wrapped.py"]
