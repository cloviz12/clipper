FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates \
 && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV CLIPPER_DATOS=/datos PYTHONUNBUFFERED=1
VOLUME /datos
CMD ["python", "main.py"]
