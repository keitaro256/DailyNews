FROM python:3.12-slim

WORKDIR /app

# tzdata để TZ=Asia/Ho_Chi_Minh hoạt động chính xác
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 8765
ENV APP_TZ=Asia/Ho_Chi_Minh
ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
