FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY app /app/app
COPY backend /app/backend
COPY worker /app/worker

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.hostel_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
