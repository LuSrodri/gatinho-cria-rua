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

# 16 fotos: a primeira em 1s e as outras quinze em 2s, dando 31s de vídeo.
#
# 2s por foto (e não 4s) porque o formato passou a ser o produto. A 4s a foto
# respirava, mas o Short inteiro cabia em oito imagens — e oito imagens em 32s
# lê como apresentação de slides. A 2s o corte vira o ritmo: dezesseis fotos
# passam no tempo em que oito passavam, o dia dele ganha etapas intermediárias
# (o portão, o encontro, a volta) e nenhum quadro fica na tela tempo suficiente
# para o olho começar a esperar o próximo.
#
# A PRIMEIRA em 1s por causa do loop. O Short reinicia sozinho, então o corte
# mais importante do vídeo é o do último quadro para o primeiro — e é o único
# que o espectador vê duas vezes. Uma abertura curta atravessa depressa o
# território já conhecido e devolve o vídeo ao movimento antes de dar tempo de
# reconhecer que ele recomeçou.
#
# Estes números andam juntos com a barra de stories, as legendas e o tamanho da
# trilha, todos calculados a partir de DURACOES/INICIOS.
TOTAL_IMAGENS = 16
DUR_IMAGEM = 2.0
DUR_PRIMEIRA = 1.0

# Duração de cada foto e o instante em que ela entra. Tudo que precisa de tempo
# no pipeline lê destas duas listas, e não de uma multiplicação por índice: as
# fotos não têm mais todas o mesmo tamanho.
DURACOES = [DUR_PRIMEIRA] + [DUR_IMAGEM] * (TOTAL_IMAGENS - 1)
INICIOS = [sum(DURACOES[:i]) for i in range(TOTAL_IMAGENS)]
DUR_TOTAL = sum(DURACOES)

# Sobreposição da volta do loop, em segundos. A trilha é pedida com DUR_TOTAL +
# CAUDA_LOOP de duração, e os últimos CAUDA_LOOP segundos são cruzados por cima
# do começo dela (ver o filtro de áudio em video.py). O resultado é que o
# instante seguinte ao último quadro já é o primeiro, sem emenda audível — e sem
# o fade de saída, que era o aviso mais claro de que o vídeo ia acabar.
CAUDA_LOOP = 2.0

# Os 16 momentos do dia dele, na ordem. A rotina é FIXA de propósito — é o que
# faz o canal ter formato reconhecível: o espectador sabe que começa no fim da
# tarde e termina no busão. O que muda todo dia são os quatro beats do rolê
# (índices 7 a 10), onde o roteirista tem liberdade total, e o recheio dos
# âncoras, que é sorteado em variacao.py.
#
# O último beat e o primeiro são vizinhos, não pontas: ele pega o busão para a
# escola e a foto seguinte é a de acordar. É o mesmo ciclo recomeçando, e é o
# que faz o loop fechar sem que nada precise anunciar o fim.
BEATS = [
    ("acordar", "Ele acorda no fim da tarde, sol baixo entrando pela janela do quarto."),
    ("espreguicar", "Ainda mole, no lugar onde acordou, olhando a rua no fim da tarde."),
    ("cafe", "O café dele, na laje ou na janela, com o pôr do sol na cidade ao fundo."),
    ("portao", "Ele saindo de casa, o portão e a calçada banhados de sol baixo."),
    ("chamar_black", "Ele vai chamar o Black, o amigo gato preto simpático, na rua."),
    ("encontro", "O Black aparece: os dois juntos, o céu já virando anoitecer."),
    ("rua", "Os dois pela rua enquanto as primeiras luzes do bairro acendem."),
    ("role_1", "Primeiro momento do rolê da noite: eles chegam no lugar."),
    ("role_2", "Segundo momento do rolê — a coisa acontecendo."),
    ("role_3", "Terceiro momento do rolê: o auge da noite."),
    ("role_4", "Quarto momento do rolê, o desfecho do que aconteceu."),
    ("madrugada", "Madrugada alta, o clima baixando, a rua vazia e quieta."),
    ("volta", "Os dois voltando a pé, o céu começando a clarear no fundo."),
    ("nascer_do_sol", "O nascer do sol pegando os dois, fim da noite."),
    ("ponto", "O ponto de ônibus, ele esperando com a luz nova da manhã."),
    ("busao", "Ele pegando o busão para a escola, sem ter dormido."),
]

# Índices dos quatro beats do rolê — o único trecho em que o roteirista inventa
# o lugar e o acontecimento. Roteiro e prompt de imagem leem daqui.
BEATS_ROLE = (7, 8, 9, 10)


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
