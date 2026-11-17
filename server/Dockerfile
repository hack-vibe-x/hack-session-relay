FROM python:3.12-slim
WORKDIR /app
COPY app.py media.py store.py ./
ENV PYTHONUNBUFFERED=1
# Listen on all interfaces inside the container; app.py defaults to 127.0.0.1 for local runs.
ENV HOST=0.0.0.0
# Railway sets PORT and, with a volume attached, RAILWAY_VOLUME_MOUNT_PATH (used as the data folder).
CMD ["python", "app.py"]
