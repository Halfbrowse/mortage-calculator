FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# --with-deps installs all required system libraries for Chromium
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps

COPY main.py database.py scraper.py ./

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "main:app"]
