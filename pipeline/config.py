"""Configuração do canal Gatinho Cria da Rua, lida do ambiente/.env."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
ENV_PATH = RAIZ / ".env"


def atualizar_env(chave: str, valor: str) -> None:
    """Cria ou atualiza ``chave=valor`` no ``.env`` local.

    Só é usado pelo fluxo de autorização do YouTube (``--auth-youtube``), que
    roda na máquina do dono. No Render não existe .env: as variáveis chegam
    pelo ambiente do serviço.
    """
    linhas = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    nova = f"{chave}={valor}"
    for i, linha in enumerate(linhas):
        if linha.startswith(f"{chave}="):
            linhas[i] = nova
            break
    else:
        if linhas and linhas[-1].strip():
            linhas.append("")
        linhas.append(nova)
    ENV_PATH.write_text("\n".join(linhas) + "\n", encoding="utf-8")


# ---- Formato do Short --------------------------------------------------------

# 8 imagens × 2,5s = 20s. Os três números andam juntos: mexer em um sem mexer
# nos outros desalinha a barra de stories, as legendas e a trilha, que são
# calculadas a partir deles.
TOTAL_IMAGENS = 8
DUR_IMAGEM = 2.5
DUR_TOTAL = TOTAL_IMAGENS * DUR_IMAGEM

# Os 8 momentos do dia dele, na ordem. A rotina é FIXA de propósito — é o que
# faz o canal ter formato reconhecível: o espectador sabe que começa no fim da
# tarde e termina no busão. O que muda todo dia são os três beats do rolê
# (índices 3, 4 e 5), onde o roteirista tem liberdade total.
BEATS = [
    ("acordar", "Ele acorda no fim da tarde, sol baixo entrando pela janela do quarto."),
    ("cafe", "O café dele, na laje ou na janela, com o pôr do sol na cidade ao fundo."),
    ("chamar_black", "Ele vai chamar o Black, o amigo gato preto simpático, na rua."),
    ("role_1", "Primeiro momento do rolê da noite."),
    ("role_2", "Segundo momento do rolê — o auge da noite."),
    ("role_3", "Terceiro momento do rolê, já na madrugada, o clima baixando."),
    ("nascer_do_sol", "O nascer do sol pegando os dois, fim da noite."),
    ("busao", "Ele pegando o busão para a escola, sem ter dormido."),
]

# Índices dos beats em que o Black aparece por definição do roteiro. Serve para
# saber quando vale gastar a imagem de referência dele (ver imagens.py).
BEATS_COM_BLACK = {2, 6}


@dataclass
class Config:
    openai_api_key: str
    elevenlabs_api_key: str

    # Vídeo
    video_largura: int = 1080
    video_altura: int = 1920
    fps: int = 30

    # Modelos
    text_model: str = "gpt-5.6-luna"
    imagem_model: str = "gpt-image-2"
    imagem_qualidade: str = "high"
    # Único tamanho retrato homologado do gpt-image-2 (2:3). O corte para 9:16
    # acontece no ffmpeg (video.py).
    imagem_tamanho: str = "1024x1536"
    musica_model: str = "music_v1"

    # YouTube
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    youtube_privacy: str = "public"
    youtube_category_id: str = "15"  # 15 = Pets & Animals

    # Caminhos
    saida: Path = field(default_factory=lambda: RAIZ / "output")
    referencia: Path = field(default_factory=lambda: RAIZ / "assets" / "estetica.png")
    fontes: Path = field(default_factory=lambda: RAIZ / "fonts")
    registro_path: Path = field(default_factory=lambda: RAIZ / "videos.txt")

    # Identidade do canal (usada na barra de stories e no @ do vídeo)
    handle: str = "@gatinhocriadarua"


def carregar_config() -> Config:
    load_dotenv(ENV_PATH)

    faltando = [
        chave
        for chave in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY")
        if not os.getenv(chave)
    ]
    if faltando:
        raise SystemExit(
            "Variáveis obrigatórias ausentes: "
            + ", ".join(faltando)
            + ". Configure o .env (local) ou as env vars do serviço (Render)."
        )

    cfg = Config(
        openai_api_key=os.environ["OPENAI_API_KEY"],
        elevenlabs_api_key=os.environ["ELEVENLABS_API_KEY"],
        video_largura=int(os.getenv("VIDEO_LARGURA", "1080")),
        video_altura=int(os.getenv("VIDEO_ALTURA", "1920")),
        fps=int(os.getenv("VIDEO_FPS", "30")),
        text_model=os.getenv("TEXT_MODEL", "gpt-5.6-luna"),
        imagem_model=os.getenv("IMAGEM_MODEL", "gpt-image-2"),
        imagem_qualidade=os.getenv("IMAGEM_QUALIDADE", "high"),
        musica_model=os.getenv("ELEVENLABS_MUSIC_MODEL", "music_v1"),
        youtube_client_id=os.getenv("YOUTUBE_CLIENT_ID", ""),
        youtube_client_secret=os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        youtube_refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
        youtube_privacy=os.getenv("YOUTUBE_PRIVACY", "public"),
        youtube_category_id=os.getenv("YOUTUBE_CATEGORY_ID", "15"),
    )
    cfg.saida.mkdir(parents=True, exist_ok=True)
    return cfg
