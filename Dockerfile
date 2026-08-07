FROM python:3.12-slim

# ffmpeg/ffprobe montam o vídeo (pipeline/video.py). O pacote já traz o libass e
# o fontconfig, que são o que queima as legendas com a Poppins do repo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
