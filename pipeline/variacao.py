"""O sorteio do dia: o que muda de uma execução para a outra.

O canal vive de uma tensão: a rotina precisa ser SEMPRE a mesma (é o que faz o
espectador reconhecer o formato em dois segundos), mas quatro vídeos por dia com
a mesma rotina viram o mesmo vídeo quatro vezes. Deixar essa variedade por conta
do modelo não resolve — pedir "seja criativo" a um LLM devolve a média dele, que
é justamente o lugar-comum.

Então a variedade é sorteada AQUI, em Python, e entra no prompt como fato dado:
hoje o tempo é este, hoje quem aparece é fulano, hoje o humor dele é este. O
modelo não escolhe o tempero — ele escreve em cima do tempero.

O que é sorteado (o recheio):
  clima, calendário do bairro, humor, forma do rolê, tempero, elenco de apoio,
  variantes dos beats-âncora e o movimento de câmera de cada foto.

O que NUNCA é sorteado (o esqueleto):
  os 8 beats, a estética, a voz das legendas, o gato, o Black e a trilha.

A semente é a data + a hora do run, então:
  - as quatro execuções de um mesmo dia saem diferentes;
  - um run é reproduzível — a semente vai no log e recriar o dia é sortear com
    ela de novo.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime

# ---- Elenco recorrente -------------------------------------------------------

# Personagens de apoio. Elenco FIXO e pequeno de propósito: quem assiste dois
# vídeos na semana reconhece a Mel e o Seu Bigode, e reconhecer é o que faz um
# bairro parecer um bairro. O que o sorteio decide é quem aparece HOJE.
#
# `visual` é em inglês porque vai direto para o gpt-image-2, do mesmo jeito que
# o bloco do Black em imagens.py.


@dataclass(frozen=True)
class Personagem:
    chave: str  # como o roteiro deve chamá-lo (e como imagens.py o encontra)
    resumo: str  # PT, para o roteirista
    visual: str  # EN, para o modelo de imagem


ELENCO = [
    Personagem(
        "Mel",
        "gata calico do sobrado azul da esquina. Mimada, dona da rua, finge que "
        "não liga para os dois mas sempre aparece.",
        "MEL — a calico cat: white with clean orange and black patches, plump and "
        "very well groomed, green eyes, a thin pink collar with a tiny bell. She "
        "clearly lives indoors. A REAL cat with normal cat anatomy.",
    ),
    Personagem(
        "Pipoca",
        "filhote cinza atrapalhado que segue os dois de longe achando que ninguém "
        "reparou. Quer ser grande.",
        "PIPOCA — a small grey tabby kitten, fluffy and clumsy, oversized ears, "
        "wide curious blue-grey eyes. Very young. A REAL kitten with normal cat "
        "anatomy.",
    ),
    Personagem(
        "Seu Bigode",
        "gato branco velho que dorme no capô morno do carro da padaria. Fala pouco "
        "e sabe tudo do bairro.",
        "SEU BIGODE — an old white cat, thick fluffy coat, very long whiskers, one "
        "ear slightly torn, calm amber eyes, a little heavy. A REAL cat with "
        "normal cat anatomy.",
    ),
    Personagem(
        "Nescau",
        "vira-lata caramelo do portão verde. Cachorro, mas amigo de infância — a "
        "rua inteira acha graça.",
        "NESCAU — a friendly caramel-coloured mixed-breed street dog, medium size, "
        "floppy ears, healthy shiny coat, always looking happy. A REAL dog with "
        "normal dog anatomy.",
    ),
    Personagem(
        "Dona Cida",
        "a senhora que deixa comida na calçada todo fim de tarde. Nunca aparece o "
        "rosto — só as mãos, o chinelo, a barra do vestido.",
        "DONA CIDA — an elderly neighbour, seen only partially and never her face: "
        "her hands putting down a bowl, her sandals and the hem of a floral dress, "
        "or her silhouette in a lit doorway. Warm and gentle presence.",
    ),
    Personagem(
        "Tico",
        "gato rajado cinza que mora na oficina e entende de tudo que tem motor. "
        "Sempre com uma mancha de graxa.",
        "TICO — a grey mackerel tabby cat, wiry and alert, with a small dark smudge "
        "on his muzzle, bright green eyes. A REAL cat with normal cat anatomy.",
    ),
]

# ---- As tabelas do sorteio ---------------------------------------------------

# Todo clima daqui é BONITO. Não é o tempo que faz a foto ser bonita, é a luz que
# ele produz: por isso cada entrada já vem com a consequência visual junto.
CLIMAS = [
    (
        "céu limpo de brigadeiro, ar lavado, tudo nítido até o horizonte",
        "crystal-clear sky, exceptionally clean air, distant skyline sharp and blue",
    ),
    (
        "a garoa fina acabou de parar e o asfalto está espelhando as luzes",
        "the light drizzle has just stopped: wet asphalt mirroring every light, "
        "glossy reflections, droplets on leaves and railings",
    ),
    (
        "neblina baixa e dourada, do tipo que some às oito da manhã",
        "low golden mist hanging between the houses, sunbeams cutting through it in "
        "visible shafts",
    ),
    (
        "vento morno levantando as folhas e balançando o varal",
        "warm breeze: leaves and laundry lifting, tree shadows moving on the walls",
    ),
    (
        "nuvens altas cor de algodão rosa cobrindo o céu inteiro",
        "high cotton-candy clouds, the whole sky washed in pink and lilac",
    ),
    (
        "calor de rachar, com as árvores fazendo sombra desenhada na calçada",
        "hot still air, dappled tree shade drawing patterns on the pavement, heat "
        "shimmer far down the street",
    ),
    (
        "chuva de verão vista de baixo do toldo, cheiro de terra molhada",
        "warm summer rain seen from under an awning, backlit raindrops, everything "
        "green and saturated, steam rising off the warm ground",
    ),
    (
        "friozinho seco, céu muito azul e o sol raso deixando tudo recortado",
        "dry cool air, deep blue sky, low raking sunlight carving long clean shadows",
    ),
]

# O calendário do bairro, por mês. Não é enfeite: é o que faz cada época do ano
# ter cara própria sem mexer em nada da rotina.
CALENDARIO = {
    1: "verão cheio, mangueiras carregadas, chuva forte no fim da tarde, hortênsias azuis nos muros",
    2: "verão, resto de carnaval de rua no bairro, bandeirinha esquecida, calor úmido",
    3: "começo do outono, luz mais dourada e mais baixa, primeiras folhas na calçada",
    4: "outono, calçadas cobertas de folha seca, manhãs de neblina, tarde curta",
    5: "friozinho chegando, fumaça de caldo na esquina, casacos no varal",
    6: "festa junina no bairro: bandeirinhas atravessando a rua, luzinha amarela, milho e quentão",
    7: "sol seco e céu muito limpo, pipas altas no fim da tarde, ipês-brancos floridos",
    8: "os ipês-amarelos explodindo em flor, vento seco, calçada coberta de pétala amarela",
    9: "primavera: ipês-roxos, quaresmeiras e manacás florindo em todas as ruas",
    10: "primavera cheia, jacarandás roxos, chuvas voltando, tudo verde e novo",
    11: "dias longos, quaresmeiras roxas, cheiro de grama cortada na praça",
    12: "pisca-pisca de natal nos portões e nas árvores da rua, calor, presépio na praça",
}

# O humor dele hoje. Colore as legendas sem mudar a voz.
HUMORES = [
    "contemplativo: ele repara mais do que comenta",
    "animado e falante, do jeito dele — ainda curto, mas com energia",
    "com uma saudade leve de algo que ele não nomeia",
    "grato, reparando no que está dando certo",
    "curioso, atrás de entender uma coisa que viu",
    "preguiçoso e confortável, sem pressa nenhuma",
    "orgulhoso de um detalhe pequeno do bairro",
    "carinhoso com todo mundo, meio bobo",
]

# A forma narrativa dos três beats do rolê. É o que garante começo-meio-fim em
# vez de três fotos soltas — e é aqui que o "acontece alguma coisa" mora.
FORMAS = [
    "um REENCONTRO: eles cruzam com alguém que fazia tempo que não apareciam",
    "uma DESCOBERTA: acham um canto do bairro que nem eles conheciam",
    "uma AJUDA: alguém está com um probleminha e os dois resolvem",
    "uma CONQUISTA pequena: eles queriam uma coisa e conseguem",
    "uma CELEBRAÇÃO: alguém do bairro está comemorando e eles caem dentro",
    "uma ESPERA: os dois esperam uma coisa acontecer, e ela acontece",
    "um TRABALHO: eles dão uma força em algo e são pagos em comida",
    "um SEGREDO: o Black conta uma coisa que estava guardando",
    "uma APRESENTAÇÃO: o Black apresenta alguém novo do bairro",
    "um CUIDADO: eles tomam conta de alguém menor pelo resto da noite",
]

# O tempero: um fio solto que atravessa as 8 fotos. Uma coisa só, pequena.
TEMPEROS = [
    "ele está juntando dinheiro (do jeito dele) para alguma coisa",
    "ele achou um objeto no caminho e carrega o dia inteiro",
    "é aniversário de alguém do bairro",
    "ele está com uma música grudada na cabeça desde que acordou",
    "alguém da rua está de mudança",
    "tem um cheiro no ar que ele reconhece e não sabe de onde",
    "ele prometeu uma coisa ontem e cumpre hoje",
    "é o último dia de alguma coisa no bairro",
    "ele está estreando uma coisa (lugar novo, caminho novo, jeito novo)",
    "tem prova na escola de manhã e ele não estudou",
]

# Variantes dos beats-âncora. A FUNÇÃO do beat não muda nunca; o detalhe, sim.
ANCORAS = {
    "onde ele acorda": [
        "no sofá velho da varanda",
        "em cima do muro ainda morno de sol",
        "dentro do cesto de roupa limpa",
        "no banco da praça, debaixo da árvore",
        "numa caixa de papelão na garagem aberta",
        "no capô de um carro estacionado",
        "na rede da laje",
        "no parapeito da janela, atrás da cortina",
        "no meio dos vasos de samambaia",
    ],
    "o que tem no café dele": [
        "pão na chapa com muita manteiga",
        "um pedaço de bolo de fubá",
        "café coado no pano, forte",
        "biscoito de polvilho",
        "mingau ainda quente",
        "pão de queijo pequeno",
        "café com leite em copo americano",
        "uma banana e um resto de bolacha",
    ],
    "como ele chama o Black": [
        "mia do alto do muro até o outro aparecer",
        "joga uma pedrinha na janela",
        "espera encostado no portão, sem pressa",
        "assobia do jeito que só os dois entendem",
        "sobe na caixa d'água para enxergar longe",
        "bate na grade com a pata, três vezes",
    ],
    "de onde ele vê o nascer do sol": [
        "da laje mais alta da rua",
        "de cima da passarela",
        "da arquibancada da quadra",
        "do último degrau da escadaria",
        "de cima da caixa d'água",
        "do banco da praça, os dois calados",
        "do próprio ponto de ônibus",
    ],
    "o detalhe do busão": [
        "o primeiro busão do dia, quase vazio",
        "o busão lotado, ele espremido na janela",
        "o busão que passa na frente da padaria e entra cheirando a pão",
        "o motorista que já conhece ele e nem cobra",
        "a janela aberta e o vento na cara",
        "o banco do fundo, o preferido dele",
    ],
}

# Quantas fotos são de OUTROS gatos (o resto é selfie). Faixa, não número fixo:
# um vídeo com 3 selfies e outro com 5 já parecem vídeos diferentes.
FAIXA_OUTROS = (3, 5)

# Chance de ter alguém do elenco no rolê de hoje. Não é 100% porque noite de
# rolê só dos dois também precisa existir — senão a "visita" deixa de ser visita.
CHANCE_CONVIDADO = 0.7


# ---- Movimento de câmera -----------------------------------------------------

# Amplitudes do zoom lento de cada foto, e o quanto do espaço disponível a
# câmera pode varrer. Suave de propósito: movimento que se percebe vira efeito,
# e o vídeo tem que continuar parecendo um story, não um trailer.
ZOOM_BASE = 1.08  # piso do zoom — precisa sobrar margem para o pan existir
ZOOM_AMPLITUDE = (0.06, 0.13)
PAN_FRACAO = (0.0, 0.75)  # fração da margem disponível que o pan realmente usa

DIRECOES = [
    (0, 0),  # parado no centro
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]


@dataclass(frozen=True)
class Movimento:
    """O Ken Burns de uma foto, em números que o ffmpeg entende."""

    z_ini: float
    z_fim: float
    dir_x: int
    dir_y: int
    pan: float  # fração de PAN_FRACAO já sorteada


@dataclass
class Variacao:
    """Tudo que muda de uma execução para a outra."""

    semente: str
    clima: str
    clima_en: str
    calendario: str
    humor: str
    forma: str
    tempero: str
    ancoras: dict[str, str]
    convidado: Personagem | None
    quantas_outros: int
    movimentos: list[Movimento] = field(default_factory=list)

    def resumo(self) -> str:
        """Uma linha por item sorteado, para o log da execução."""
        visita = self.convidado.chave if self.convidado else "ninguém (só os dois)"
        return "\n".join(
            f"  {rotulo}: {valor}"
            for rotulo, valor in (
                ("semente", self.semente),
                ("tempo", self.clima),
                ("época", self.calendario),
                ("humor", self.humor),
                ("rolê", self.forma),
                ("tempero", self.tempero),
                ("visita", visita),
                ("fotos de outros", str(self.quantas_outros)),
            )
        )


def _movimentos(rng: random.Random, total: int) -> list[Movimento]:
    """Sorteia o movimento de cada foto, sem repetir o anterior.

    A regra de não repetir é o ponto: oito fotos com o mesmo zoom dão sensação
    de esteira transportadora, e é isso que denuncia que o vídeo é montado.
    """
    movimentos: list[Movimento] = []
    fecha = rng.random() < 0.5
    anterior = None
    for _ in range(total):
        amplitude = rng.uniform(*ZOOM_AMPLITUDE)
        z_ini, z_fim = (
            (ZOOM_BASE, ZOOM_BASE + amplitude)
            if fecha
            else (ZOOM_BASE + amplitude, ZOOM_BASE)
        )
        opcoes = [d for d in DIRECOES if d != anterior]
        direcao = rng.choice(opcoes)
        anterior = direcao
        movimentos.append(
            Movimento(z_ini, z_fim, direcao[0], direcao[1], rng.uniform(*PAN_FRACAO))
        )
        # Alterna a direção do zoom na maior parte das vezes, mas nem sempre:
        # alternância perfeita é um padrão, e padrão também fica previsível.
        fecha = not fecha if rng.random() < 0.75 else fecha
    return movimentos


def sortear(total_fotos: int, quando: datetime | None = None) -> Variacao:
    """Sorteia o dia de hoje. A semente é a data + a hora do run."""
    agora = quando or datetime.now()
    semente = agora.strftime("%Y-%m-%d-%H")
    rng = random.Random(semente)

    clima, clima_en = rng.choice(CLIMAS)
    convidado = rng.choice(ELENCO) if rng.random() < CHANCE_CONVIDADO else None

    return Variacao(
        semente=semente,
        clima=clima,
        clima_en=clima_en,
        calendario=CALENDARIO[agora.month],
        humor=rng.choice(HUMORES),
        forma=rng.choice(FORMAS),
        tempero=rng.choice(TEMPEROS),
        ancoras={rotulo: rng.choice(opcoes) for rotulo, opcoes in ANCORAS.items()},
        convidado=convidado,
        quantas_outros=rng.randint(*FAIXA_OUTROS),
        movimentos=_movimentos(rng, total_fotos),
    )
