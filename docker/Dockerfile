FROM python:3.10-slim-bullseye

WORKDIR /app

COPY ./internal .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
