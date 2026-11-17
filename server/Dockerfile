FROM python:3.12-slim
WORKDIR /app
COPY app.py .
ENV PYTHONUNBUFFERED=1
# Railway sets PORT and, with a volume attached, RAILWAY_VOLUME_MOUNT_PATH (used as the data folder).
CMD ["python", "app.py"]
