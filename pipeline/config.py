"""Configuração do canal Gatinho Cria da Rua, lida do ambiente/.env."""

import math
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

# 16 fotos em 31s. A PRIMEIRA dura sempre 1s; as outras quinze duram entre 1,3s
# e 3,5s, e quem decide qual dura quanto é a HISTÓRIA daquele dia (o roteirista
# devolve um peso por cena, ver roteiro.py, e `montar_ritmo` transforma esses
# pesos em segundos).
#
# Antes eram 2s cravados para todas. O problema de 2s cravados não é a duração,
# é a REGULARIDADE: um corte exatamente a cada dois segundos, dezesseis vezes,
# vira metrônomo — o olho aprende o intervalo em três fotos e passa a esperar o
# próximo corte em vez de olhar a foto. Ritmo irregular é o oposto disso: a foto
# que carrega a piada do rolê fica na tela o tempo de a piada acontecer, e as
# fotos de passagem passam mesmo. O corte volta a ser pontuação em vez de
# batida.
#
# A PRIMEIRA em 1s por causa do loop. O Short reinicia sozinho, então o corte
# mais importante do vídeo é o do último quadro para o primeiro — e é o único
# que o espectador vê duas vezes. Uma abertura curta atravessa depressa o
# território já conhecido e devolve o vídeo ao movimento antes de dar tempo de
# reconhecer que ele recomeçou.
TOTAL_IMAGENS = 16
DUR_PRIMEIRA = 1.0
DUR_MINIMA = 1.3
DUR_MAXIMA = 3.5

# O total é FIXO em 31s, mesmo com as fotos variando. Não é teimosia com o
# número: o orçamento fechado é o que mantém o resto do pipeline determinístico
# — a trilha é encomendada com este tamanho antes de o vídeo existir, e o loop
# de áudio depende de saber a duração exata de antemão. O que a história decide
# é como repartir os 31s, não quantos são.
DUR_TOTAL = 31.0

# Sobreposição da volta do loop, em segundos. A trilha é entregue com DUR_AUDIO +
# CAUDA_LOOP de duração, e os últimos CAUDA_LOOP segundos são cruzados por cima
# do começo dela (ver o filtro de áudio em video.py). O resultado é que o
# instante seguinte ao último quadro já é o primeiro, sem emenda audível — e sem
# o fade de saída, que era o aviso mais claro de que o vídeo ia acabar.
CAUDA_LOOP = 2.0

# A faixa de áudio termina 1,4ms ANTES do vídeo, e isso é de propósito.
#
# O AAC codifica em blocos de 1024 amostras e não sabe fazer bloco pela metade:
# uma faixa que não termina em bloco cheio é completada com ZEROS pelo encoder.
# Com 31s a 44.100 Hz dá 1.367.100 amostras, que são 1335,06 blocos — e os 964
# zeros do bloco que faltava viram 19ms de silêncio digital no fim do arquivo.
# Isso foi medido no .mp4 pronto, decodificando o áudio de volta; não aparece em
# lugar nenhum antes disso, nem na trilha, nem no filtro, nem no log do ffmpeg.
#
# Dezenove milissegundos parecem nada, mas caem no ÚNICO lugar do vídeo onde não
# podem cair: o Short reinicia sozinho, então esse silêncio fica exatamente entre
# a última amostra e a primeira. É um buraco no ponto que todo o resto deste
# projeto existe para esconder.
#
# Não dá para alinhar as três coisas ao mesmo tempo: uma duração múltipla de 1/30
# de segundo E de 1024/44100 tem que ser múltipla de 17,067s, e 31 não é. Então o
# vídeo fica com os 31s cravados e o ÁUDIO é encurtado até o bloco fechado
# anterior — 62 amostras a menos, 1,4ms, menos que um ciclo de um som grave.
#
# Encurtar, e não esticar até o bloco seguinte. Esticar também acaba com o
# silêncio, mas deixa o áudio mais longo que o vídeo, e aí o `-frames:v` encerra
# a saída no último quadro de imagem e apara a faixa de volta — para um tamanho
# que não é nenhum dos dois, e que só se descobre medindo o arquivo pronto.
# Ficando abaixo do vídeo, o áudio nunca é a faixa que manda, e o que sai é
# exatamente o que está escrito aqui.
#
# DUR_AUDIO, e não DUR_TOTAL, é a duração real do laço de áudio: é ela que a
# trilha repete quando o Short recomeça, e é a ela que musica.py alinha os
# compassos.
TAXA_AUDIO = 44100
BLOCO_AAC = 1024
AMOSTRAS_LOOP = round(DUR_TOTAL * TAXA_AUDIO) // BLOCO_AAC * BLOCO_AAC
DUR_AUDIO = AMOSTRAS_LOOP / TAXA_AUDIO


@dataclass(frozen=True)
class Ritmo:
    """Quanto tempo cada foto fica na tela, e quando ela entra.

    Tudo que precisa de tempo no pipeline (a barra de stories, as legendas, o
    movimento de câmera) lê daqui, e não de uma multiplicação por índice: as
    fotos não têm mais todas o mesmo tamanho, e as durações não são nem números
    redondos.
    """

    duracoes: list[float]
    inicios: list[float]
    total: float

    def __len__(self) -> int:
        return len(self.duracoes)

    def resumo(self) -> str:
        return " ".join(f"{d:.2f}" for d in self.duracoes)


def _repartir(pretendidas: list[float], orcamento: float) -> list[float]:
    """Encaixa as durações pretendidas em ``orcamento`` segundos, dentro dos limites.

    O roteirista não devolve segundos, devolve o ritmo de cada cena; roteiro.py
    traduz cada ritmo para a duração PRETENDIDA dele (1,4s para uma passagem,
    3,4s para o momento da história). Se a distribuição do dia for a esperada,
    essas durações já somam mais ou menos os 30s disponíveis e cada foto fica com
    o tempo que pediu. Quando não somam — o dia em que o modelo marca metade das
    cenas como longas —, todas são multiplicadas pelo mesmo fator até caberem.

    Achar esse fator é o problema inteiro, porque a soma depois do corte nos
    limites não é proporcional ao fator: passado certo ponto, esticar mais não
    aumenta nada, porque quem cresceria já bateu no teto. Mas a soma É monótona
    no fator, e vai de ``n * DUR_MINIMA`` (fator perto de zero) a
    ``n * DUR_MAXIMA`` (fator enorme) — e o orçamento está garantidamente entre
    os dois (com 15 fotos e 30s: entre 19,5s e 52,5s). Então existe um fator que
    acerta a soma na mosca, e bisseção o encontra em oitenta iterações de uma
    linha cada.

    A alternativa óbvia — repartir proporcionalmente e ir congelando quem estoura
    — foi o que estava aqui antes, e ela tem um caso em que devolve uma soma
    errada em silêncio: se numa rodada uns estouram o teto e outros furam o piso,
    a lista inteira é congelada de uma vez e o que sobrou do orçamento não vai
    para lugar nenhum. Com um peso muito maior que os outros, isso dava 22,7s de
    fotos para 31s de áudio.
    """
    if not pretendidas:
        return []
    # Duração pretendida ausente, zerada ou negativa não deve engolir o vídeo nem
    # sumir dele: sem informação, vale a média das outras.
    validas = [v for v in pretendidas if v > 0]
    media = sum(validas) / len(validas) if validas else 1.0
    pretendidas = [v if v > 0 else media for v in pretendidas]

    def soma(fator: float) -> float:
        return sum(min(max(v * fator, DUR_MINIMA), DUR_MAXIMA) for v in pretendidas)

    baixo, alto = 1e-6, 1e6
    for _ in range(80):
        meio = (baixo + alto) / 2
        if soma(meio) < orcamento:
            baixo = meio
        else:
            alto = meio
    fator = (baixo + alto) / 2
    return [min(max(v * fator, DUR_MINIMA), DUR_MAXIMA) for v in pretendidas]


def montar_ritmo(pretendidas: list[float], fps: int) -> Ritmo:
    """Converte as durações pretendidas pelo roteiro em durações somando DUR_TOTAL.

    As durações são arredondadas para QUADRO INTEIRO, e não para um decimal
    bonito. O ffmpeg monta cada foto com `round(duracao * fps)` quadros, então
    uma duração que não cai em quadro cheio vira erro de arredondamento — e como
    os instantes de entrada são acumulados, esse erro SOMA: dezesseis fotos com
    meio quadro de sobra cada põem a legenda e a barra de stories quase um terço
    de segundo à frente da imagem no fim do vídeo. Quantizando aqui, o tempo do
    filtro e o tempo do arquivo .ass são o mesmo tempo por construção.
    """
    duracoes = _repartir(pretendidas[1:], DUR_TOTAL - DUR_PRIMEIRA)

    # Daqui para baixo a conta é toda em QUADROS, e os limites também. Converter
    # os limites junto não é preciosismo: a 24 fps, `round(1,3 * 24)` são 31
    # quadros, que valem 1,29s — o arredondamento sozinho já sairia por baixo do
    # piso que a repartição tinha respeitado.
    q_minimo = math.ceil(DUR_MINIMA * fps)
    q_maximo = math.floor(DUR_MAXIMA * fps)
    quadros = [round(DUR_PRIMEIRA * fps)] + [
        min(max(round(d * fps), q_minimo), q_maximo) for d in duracoes
    ]

    # Os quadros perdidos (ou ganhos) no arredondamento são devolvidos um a um
    # às fotos mais longas, que é onde um quadro a mais ou a menos não se vê. A
    # primeira foto fica de fora: 1s cravado é o que faz a abertura do loop
    # funcionar. A rodada que não consegue mexer em nada encerra o ajuste —
    # acontece se todas as fotos já estiverem no limite, e aí não há o que fazer.
    sobra = round(DUR_TOTAL * fps) - sum(quadros)
    passo = 1 if sobra > 0 else -1
    ajustaveis = sorted(range(1, len(quadros)), key=lambda i: -quadros[i])
    while sobra:
        andou = False
        for alvo in ajustaveis:
            if not sobra:
                break
            if q_minimo <= quadros[alvo] + passo <= q_maximo:
                quadros[alvo] += passo
                sobra -= passo
                andou = True
        if not andou:
            break

    duracoes = [q / fps for q in quadros]
    inicios = [sum(duracoes[:i]) for i in range(len(duracoes))]
    return Ritmo(duracoes, inicios, sum(duracoes))



# Os 16 momentos do dia dele, na ordem. A rotina é FIXA de propósito — é o que
# faz o canal ter formato reconhecível: o espectador sabe que começa no fim da
# tarde e termina no busão. O que muda todo dia são os quatro beats do rolê
# (índices 7 a 10), onde o roteirista tem liberdade total, e o recheio dos
# âncoras, que é sorteado em variacao.py.
#
# O último beat e o primeiro são vizinhos, não pontas: ele pega o busão para a
# escola e a foto seguinte é a de acordar. É o mesmo ciclo recomeçando, e é o
# que faz o loop fechar sem que nada precise anunciar o fim.
#
# O beat 1 é o GANCHO, e é o único cuja função não é contar o dia: é fazer quem
# tem gato parar de rolar o feed. Ele acorda, sim — mas acorda numa situação
# absurda de gato, daquelas em que o dono se reconhece na hora ("meu gato faria
# isso"). Qual absurdo é sorteado em variacao.py; aqui só está dito que é um.
BEATS = [
    (
        "acordar",
        "O GANCHO. Ele acordando no fim da tarde numa situação absurda de gato — "
        "a posição, o lugar ou o estado em que ele está é a graça da foto, e ela "
        "tem que ser entendida em um segundo, sem legenda explicando.",
    ),
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
