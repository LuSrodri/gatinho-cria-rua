FROM python:3.12-slim

# ffmpeg/ffprobe montam o vídeo (pipeline/video.py). O pacote já traz o libass e
# o fontconfig, que são o que queima as legendas com a Poppins do repo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Sem isto o Python enfileira o stdout (a saída não é um terminal) e os logs do
# Render só aparecem quando a execução termina — um job travado fica igual a um
# job trabalhando. A execução leva minutos gerando imagem, então acompanhar o
# progresso ao vivo é o que diz se ainda está de pé.
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
