FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl libpq5 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/media /app/staticfiles
EXPOSE 8000
CMD ["gunicorn", "erp.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]

