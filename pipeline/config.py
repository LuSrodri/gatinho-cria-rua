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

# 8 fotos. A PRIMEIRA dura sempre 1s; as outras sete duram entre 1,3s e 3,5s, e
# quem decide qual dura quanto é a HISTÓRIA daquele dia (o roteirista devolve um
# ritmo por cena, ver roteiro.py, e `montar_ritmo` transforma esses ritmos em
# quadros).
#
# Eram 16, e antes disso 8. A volta para 8 não é desfazer a ida para 16: o que
# foi para 16 e ficou foi o RITMO VARIÁVEL, e é ele que faz oito fotos não serem
# as oito de antes. Com 4s cravados cada, oito fotos eram oito paradas iguais;
# com 1,3s a 3,5s decididos pela história, são oito fotos em que a que carrega o
# momento fica quase três vezes mais que a de passagem.
#
# O problema de duração cravada nunca foi a duração, foi a REGULARIDADE: um
# corte exatamente no mesmo intervalo, foto após foto, vira metrônomo — o olho
# aprende o intervalo em três fotos e passa a esperar o próximo corte em vez de
# olhar a foto. Ritmo irregular é o oposto disso: o corte volta a ser pontuação
# em vez de batida.
#
# A PRIMEIRA em 1s por causa do loop. O Short reinicia sozinho, então o corte
# mais importante do vídeo é o do último quadro para o primeiro — e é o único
# que o espectador vê duas vezes. Uma abertura curta atravessa depressa o
# território já conhecido e devolve o vídeo ao movimento antes de dar tempo de
# reconhecer que ele recomeçou.
TOTAL_IMAGENS = 8
DUR_PRIMEIRA = 1.0
DUR_MINIMA = 1.3
DUR_MAXIMA = 3.5

# O total NÃO é fixo. Era 31s cravados, e o orçamento fechado existia por um
# motivo de encanamento, não de edição: a trilha é encomendada com o tamanho do
# vídeo, e quem encomendava precisava saber esse tamanho antes de o vídeo
# existir. Isso deixou de ser verdade quando o ritmo passou a ser montado ENTRE
# o roteiro e a montagem (ver main.py) — no instante em que a trilha é pedida, as
# durações das oito fotos já estão decididas, e o tamanho do laço vai junto no
# pedido.
#
# Com o orçamento fechado, a história dizia só a PROPORÇÃO e o relógio dizia o
# resto: o dia de fotos rápidas era esticado até encher os 31s e o dia de fotos
# que pediam tempo era espremido até caber neles. Agora a história diz as duas
# coisas — o dia corrido fecha curto e o dia que respira fecha longo, e os dois
# estão certos.
#
# Os limites são de construção, não de configuração: 1s da primeira mais sete
# fotos entre 1,3s e 3,5s dão de 10,1s a 25,5s. Na distribuição comum (algumas
# corridas, várias normais, uma ou duas longas) o vídeo fecha perto de 16s.
#
# Quem precisa da duração lê `Ritmo.total`, e não uma constante: ela só existe
# depois que o roteiro do dia existe.

# Sobreposição da volta do loop, em segundos. A trilha é entregue com
# `Ritmo.audio` + CAUDA_LOOP de duração, e os últimos CAUDA_LOOP segundos são
# cruzados por cima do começo dela (ver o filtro de áudio em video.py). O
# resultado é que o instante seguinte ao último quadro já é o primeiro, sem
# emenda audível — e sem o fade de saída, que era o aviso mais claro de que o
# vídeo ia acabar.
#
# Continuam sendo 2s com o vídeo mais curto. Eles são uma fração maior do total
# (2 de 16 em vez de 2 de 31), mas o cruzamento não é medido contra o vídeo: é
# medido contra o compasso, e o que ele precisa é durar mais de um compasso para
# a passagem acontecer dentro da música em vez de em cima de uma batida só.
CAUDA_LOOP = 2.0

# A faixa de áudio termina alguns décimos de milissegundo ANTES do vídeo, e isso
# é de propósito.
#
# O AAC codifica em blocos de 1024 amostras e não sabe fazer bloco pela metade:
# uma faixa que não termina em bloco cheio é completada com ZEROS pelo encoder.
# Com os 31s de antes, a 44.100 Hz, davam 1.367.100 amostras, que são 1335,06
# blocos — e os 964 zeros do bloco que faltava viravam 19ms de silêncio digital
# no fim do arquivo. Isso foi medido no .mp4 pronto, decodificando o áudio de
# volta; não aparece em lugar nenhum antes disso, nem na trilha, nem no filtro,
# nem no log do ffmpeg.
#
# Dezenove milissegundos parecem nada, mas caem no ÚNICO lugar do vídeo onde não
# podem cair: o Short reinicia sozinho, então esse silêncio fica exatamente entre
# a última amostra e a primeira. É um buraco no ponto que todo o resto deste
# projeto existe para esconder.
#
# Não dá para alinhar as três coisas ao mesmo tempo: uma duração múltipla de 1/30
# de segundo E de 1024/44100 teria que ser múltipla de 17,067s, e a duração do
# vídeo agora é a que a história somar. Então o vídeo fica com a duração que ele
# tem e o ÁUDIO é encurtado até o bloco fechado anterior — no máximo 1023
# amostras a menos, 23ms no pior caso, e normalmente uma fração disso.
#
# Encurtar, e não esticar até o bloco seguinte. Esticar também acaba com o
# silêncio, mas deixa o áudio mais longo que o vídeo, e aí o `-frames:v` encerra
# a saída no último quadro de imagem e apara a faixa de volta — para um tamanho
# que não é nenhum dos dois, e que só se descobre medindo o arquivo pronto.
# Ficando abaixo do vídeo, o áudio nunca é a faixa que manda, e o que sai é
# exatamente o que está escrito aqui.
#
# `Ritmo.audio`, e não `Ritmo.total`, é a duração real do laço de áudio: é ela
# que a trilha repete quando o Short recomeça, e é a ela que musica.py alinha os
# compassos.
TAXA_AUDIO = 44100
BLOCO_AAC = 1024


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

    @property
    def audio(self) -> float:
        """A duração do laço de áudio: o vídeo aparado até fechar um bloco do AAC.

        Está aqui, e não numa constante, porque o vídeo deixou de ter duração
        fixa: o laço só é conhecido depois que a história decide os cortes. É
        este número que musica.py encomenda e ao qual alinha os compassos, e é
        ele que video.py usa para montar o anel — o `total` é a duração do
        VÍDEO, e usar um no lugar do outro devolve o silêncio de fim de bloco
        exatamente na volta do loop.
        """
        return round(self.total * TAXA_AUDIO) // BLOCO_AAC * BLOCO_AAC / TAXA_AUDIO


def montar_ritmo(pretendidas: list[float], fps: int) -> Ritmo:
    """Converte as durações pretendidas pelo roteiro em quadros inteiros.

    O roteirista não devolve segundos, devolve o ritmo de cada cena; roteiro.py
    traduz cada ritmo para a duração PRETENDIDA dele (1,4s para uma passagem,
    3,4s para o momento da história). Aqui cada cena recebe o que pediu, aparado
    nos limites — e a soma disso é a duração do vídeo.

    Este passo já foi bem maior. Com o total fixo em 31s, a duração pretendida
    era só uma proporção: existia uma bisseção que procurava o fator pelo qual
    multiplicar todas as cenas para a soma cair exatamente no orçamento, e
    depois uma rodada que devolvia às fotos mais longas os quadros perdidos no
    arredondamento. Nada disso tem função quando não há orçamento: o que a cena
    pediu é o que ela leva, e o vídeo dura o que der.

    O que sobreviveu é o ARREDONDAMENTO, e ele é feito em QUADRO INTEIRO, não
    num decimal bonito. O ffmpeg monta cada foto com `round(duracao * fps)`
    quadros, então uma duração que não cai em quadro cheio vira erro de
    arredondamento — e como os instantes de entrada são acumulados, esse erro
    SOMA e põe a legenda e a barra de stories à frente da imagem no fim do
    vídeo. Quantizando aqui, e derivando `inicios` e `total` da mesma contagem
    de quadros, o tempo do filtro e o tempo do arquivo .ass são o mesmo tempo por
    construção.

    Os limites também são convertidos para quadros, e isso não é preciosismo: a
    24 fps, `round(1,3 * 24)` são 31 quadros, que valem 1,29s — o arredondamento
    sozinho já sairia por baixo do piso.

    Duração pretendida ausente, zerada ou negativa cai no piso em vez de derrubar
    a execução: sem orçamento para repartir, o piso é o palpite certo para uma
    cena sobre a qual não se sabe nada.
    """
    q_minimo = math.ceil(DUR_MINIMA * fps)
    q_maximo = math.floor(DUR_MAXIMA * fps)
    quadros = [round(DUR_PRIMEIRA * fps)] + [
        min(max(round(d * fps), q_minimo), q_maximo) for d in pretendidas[1:]
    ]

    duracoes = [q / fps for q in quadros]
    inicios = [sum(quadros[:i]) / fps for i in range(len(quadros))]
    return Ritmo(duracoes, inicios, sum(quadros) / fps)



# Os 8 momentos do dia dele, na ordem. A rotina é FIXA de propósito — é o que
# faz o canal ter formato reconhecível: o espectador sabe que começa no fim da
# tarde e termina no busão. O que muda todo dia são os três beats do rolê
# (índices 3 a 5), onde o roteirista tem liberdade total, e o recheio dos
# âncoras, que é sorteado em variacao.py.
#
# Encolher de 16 para 8 foi encolher a ROTINA, não o rolê. Os beats que sumiram
# são os de passagem — espreguiçar, o portão, o encontro em si, o ponto de
# ônibus vazio —, cada um deles uma foto que só levava de um lugar ao outro. O
# rolê perdeu um dos quatro e ficou com três, que é o que uma história com
# começo, meio e fim precisa. Com metade das fotos, cada beat que ficou tem que
# carregar mais de um momento: o café é também o acordar de vez, a madrugada é
# também a volta, o busão é também o nascer do sol.
#
# A luz continua sendo o relógio do vídeo, e com 8 fotos ela anda mais depressa:
# fim de tarde, anoitecer, noite, madrugada, nascer do sol em oito passos em vez
# de dezesseis. Cada beat tem que ser inconfundível do anterior (ver ESTETICA em
# roteiro.py).
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
    (
        "cafe",
        "Ainda meio dentro da situação em que acordou, mole, com o café dele na "
        "laje ou na janela e o sol baixo na cidade ao fundo.",
    ),
    (
        "chamar_black",
        "Ele chama o Black, o amigo gato preto simpático, e os dois saem juntos "
        "pela rua — o céu virando anoitecer, as primeiras luzes acendendo.",
    ),
    ("role_1", "Primeiro momento do rolê da noite: eles chegam no lugar."),
    ("role_2", "Segundo momento do rolê — a coisa acontecendo, o auge da noite."),
    ("role_3", "Terceiro momento do rolê, o desfecho do que aconteceu."),
    (
        "madrugada",
        "Madrugada alta: os dois voltando a pé pela rua vazia e quieta, o céu "
        "começando a clarear no fundo.",
    ),
    (
        "busao",
        "Nascer do sol no ponto: ele pegando o busão para a escola, sem ter "
        "dormido, com a luz nova da manhã.",
    ),
]

# Índices dos três beats do rolê — o único trecho em que o roteirista inventa o
# lugar e o acontecimento. Roteiro e prompt de imagem leem daqui.
BEATS_ROLE = (3, 4, 5)


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
