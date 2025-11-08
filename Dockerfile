FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-k", "gthread", "-t", "120", "-b", "0.0.0.0:8000", "app:app"]
