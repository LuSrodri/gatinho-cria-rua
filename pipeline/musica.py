"""A trilha do Short, composta pela API de música da ElevenLabs.

Música gerada em vez de biblioteca de faixas por um motivo prático: faixa
licenciada de terceiro é o caminho mais curto para um Content ID em cima do
canal. O que sai daqui é instrumental, original e do tamanho exato do vídeo.
"""

from pathlib import Path

import requests

from .config import DUR_TOTAL, Config

API_MUSICA = "https://api.elevenlabs.io/v1/music"

# O prompt é fixo: a identidade sonora do canal não deve mudar a cada execução,
# do mesmo jeito que a estética visual não muda. O que varia é só a semente
# implícita da geração.
PROMPT = """\
Instrumental lo-fi hip hop for a short film about a teenage street cat wandering
the outskirts of São Paulo at golden hour and through the night.

Dusty boom-bap drums, soft and unhurried, around 75 BPM. A warm, slightly
detuned electric piano playing a simple melancholic loop. A round, gentle bass
line. Underneath it all: vinyl crackle, distant traffic, the hum of a warm
evening.

The feeling is intimate and a little wistful — nostalgic but not sad, calm but
awake. Nothing dramatic, no build, no drop. It should feel like a loop you could
stare out of a bus window to.

No vocals, no lyrics, no voices."""


def gerar_musica(cfg: Config, destino: Path) -> Path | None:
    """Compõe a trilha e devolve o caminho; None se a ElevenLabs falhar.

    Falha aqui NÃO derruba a execução: um Short mudo ainda é um Short no ar, e
    perder o vídeo inteiro por causa da trilha seria trocar um problema pequeno
    por um grande. O ffmpeg cobre o buraco com uma faixa silenciosa (video.py).
    """
    print("[musica] Compondo a trilha do vídeo...")
    try:
        resposta = requests.post(
            API_MUSICA,
            params={"output_format": "mp3_44100_128"},
            headers={
                "xi-api-key": cfg.elevenlabs_api_key,
                "Content-Type": "application/json",
            },
            json={
                "prompt": PROMPT,
                # Um pouco mais longa que o vídeo: sobra é aparada com fade no
                # ffmpeg, enquanto faixa curta demais deixaria silêncio no fim.
                "music_length_ms": int((DUR_TOTAL + 2) * 1000),
                "model_id": cfg.musica_model,
                "force_instrumental": True,
            },
            timeout=300,
        )
        if resposta.status_code == 401:
            print("[aviso] ELEVENLABS_API_KEY inválida (401); vídeo sairá mudo.")
            return None
        if resposta.status_code != 200:
            print(
                f"[aviso] ElevenLabs recusou a trilha ({resposta.status_code}): "
                f"{resposta.text[:200]}. Vídeo sairá mudo."
            )
            return None
        destino.write_bytes(resposta.content)
    except requests.RequestException as erro:
        print(f"[aviso] Falha ao compor a trilha ({erro}); vídeo sairá mudo.")
        return None

    print(f"[musica] Trilha salva em {destino.name}.")
    return destino
