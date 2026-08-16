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
  o gancho da primeira foto, clima, calendário do bairro, humor, forma do rolê,
  tempero, elenco de apoio, variantes dos beats-âncora, a escala de plano de cada
  foto e o movimento de câmera de cada foto.

O que NUNCA é sorteado (o esqueleto):
  os 16 beats, a estética, a voz das legendas, o gato, o Black e a trilha.

A semente é a data + a hora do run, então:
  - as quatro execuções de um mesmo dia saem diferentes;
  - um run é reproduzível — a semente vai no log e recriar o dia é sortear com
    ela de novo.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime

from .config import TOTAL_IMAGENS

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

# O tempero: um fio solto que atravessa as 16 fotos. Uma coisa só, pequena.
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

# ---- O gancho -----------------------------------------------------------------

# A primeira foto do Short é a única que tem uma função além de contar o dia: ela
# tem um segundo para impedir a pessoa de rolar o feed. E o que faz dono de gato
# parar não é uma foto bonita de gato — é uma foto em que ele reconhece o PRÓPRIO
# gato fazendo uma coisa que só gato faz. O comentário que se quer embaixo do
# vídeo é "meu gato faria isso kkkk", e ninguém escreve isso por causa de um
# nascer do sol.
#
# Por isso o gancho é sorteado aqui e não fica por conta do modelo. Pedir "faça
# um gancho criativo" a um LLM devolve a média dele, que é gato fofo dormindo ao
# sol — bonito e esquecível. Sorteado, o absurdo vem inteiro e específico, e o
# modelo gasta a criatividade em escrever a legenda em cima dele.
#
# A régua de cada entrada, e o que faz uma entrar nesta lista:
#
# 1. TEM QUE SER LIDA EM UM SEGUNDO. A foto abre o vídeo e dura 1s. Absurdo que
#    precisa de contexto ("ele está com ciúmes do vizinho") não cabe; absurdo de
#    POSIÇÃO e de LUGAR cabe, porque é uma silhueta.
# 2. TEM QUE SER COISA DE GATO DE VERDADE. Nada de gato fazendo coisa de gente —
#    a graça do canal é o contrário: um gato comum, com anatomia de gato, fazendo
#    exatamente o que gatos fazem, num dia que por acaso é de adolescente.
# 3. NÃO PODE SER FOFO E PRONTO. Fofo o canal já é o tempo inteiro. Aqui precisa
#    ter o desconforto cômico: o lugar errado, a posição impossível, a cara de
#    quem foi pego.
#
# O gancho substitui o antigo âncora "onde ele acorda": onde ele acorda passou a
# ser parte da piada, em vez de um detalhe ao lado dela.
GANCHOS = [
    "dormindo dentro de uma caixa de papelão pequena demais para ele, "
    "transbordando dos quatro lados, com cara de que está tudo perfeito",
    "de barriga para cima, de pernas abertas e cabeça pendurada para trás no "
    "degrau, na posição menos digna que um gato consegue",
    "espremido dentro de uma bacia de plástico redonda, moldado no formato dela",
    "dormindo em cima de um par de chinelos, ignorando a almofada macia que está "
    "ao lado, vazia",
    "sentado exatamente dentro de um quadrado desenhado no chão pelo sol da "
    "janela, do tamanho exato dele, sem encostar um fio de pelo para fora",
    "acordando dentro de um vaso de samambaia, com as folhas para todo lado e "
    "terra no bigode",
    "dormindo enfiado num saco de papel de padaria, só o rabo para fora",
    "com metade do corpo dentro de uma caixa e a outra metade escorrendo para "
    "fora, dormindo assim mesmo",
    "empoleirado num lugar impossivelmente estreito — o parapeito de dois dedos, "
    "o encosto fino da cadeira — dormindo como se fosse um colchão",
    "com a cara amassada contra o vidro da janela, dormindo grudado nele",
    "dormindo em cima do jornal aberto, exatamente por cima da parte que alguém "
    "estava lendo",
    "acordado de susto no meio de um pulo, no ar, com os olhos enormes de quem "
    "não sabe o que aconteceu",
    "dentro da caixa vazia, ao lado da caminha nova e cara que ninguém usou",
    "espalhado em cima do capô morno do carro, derretido, ocupando o capô inteiro",
    "com a pata na cara, tapando os olhos do sol, se recusando a acordar",
    "sentado como gente, encostado num degrau, com as pernas para a frente e "
    "cara de quem está pensando na vida",
    "olhando fixo para um canto vazio da parede, imóvel, sem nada ali",
    "enfiado dentro de um pé de bota velha na varanda, só as orelhas aparecendo",
    "dormindo dentro do cesto de roupa limpa, em cima da roupa dobrada, "
    "obviamente pego no flagra",
    "acordando com a marca do tapete estampada na cara inteira",
]

# Variantes dos beats-âncora. A FUNÇÃO do beat não muda nunca; o detalhe, sim.
ANCORAS = {
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
    "o que ele vê da rua quando ainda está mole": [
        "as crianças voltando da escola no fim da tarde",
        "o vizinho regando o jardim, a água escurecendo a calçada",
        "a roupa balançando no varal da laje de frente",
        "o portão da padaria sendo aberto para a noite",
        "os pardais brigando pelo último sol no fio",
        "um carro velho sendo lavado na porta de casa",
        "a sombra do ipê andando devagar pelo muro",
    ],
    "por onde eles voltam na madrugada": [
        "pela viela da escadaria, degrau por degrau",
        "pelo meio da rua vazia, os dois no asfalto",
        "pela calçada da padaria, cortando o cheiro do pão",
        "por cima dos muros, o caminho de gato",
        "pelo campinho apagado, atravessando o gramado molhado",
        "pela beira da praça, no orvalho do banco",
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

# Quantas das 16 fotos são de OUTROS gatos (o resto é selfie). Faixa, não número
# fixo: um vídeo com 6 selfies e outro com 10 já parecem vídeos diferentes.
FAIXA_OUTROS = (6, 10)

# Chance de ter alguém do elenco no rolê de hoje. Não é 100% porque noite de
# rolê só dos dois também precisa existir — senão a "visita" deixa de ser visita.
CHANCE_CONVIDADO = 0.7


# ---- Enquadramento -----------------------------------------------------------

# A ESCALA DE PLANO. Sem ela o vídeo é um slideshow, e nenhum ritmo de corte
# conserta isso.
#
# O problema era que o enquadramento estava congelado dentro dos blocos "selfie"
# e "outros" de imagens.py: TODA selfie era "low angle, close to his face" e TODA
# foto de outros era "from a short distance". Dezesseis fotos, duas distâncias.
# Aí o corte pode variar de 1,3s a 3,5s à vontade — o olho continua vendo a mesma
# imagem em tamanhos iguais, e é isso que lê como apresentação de slides. Ritmo
# visual é CONTRASTE DE ESCALA: o olho tem que reajustar a cada corte, e é o
# reajuste que dá a sensação de montagem.
#
# `familia` é o que faz o trabalho. A regra do sorteio não é "não repetir o
# enquadramento" (dois planos médios diferentes ainda são dois planos médios): é
# não repetir a FAMÍLIA, então todo corte troca de escala. Fechado nunca vem
# depois de fechado, aberto nunca depois de aberto.
#
# `so_outros` marca o que não cabe numa selfie de pata esticada: um plano em que
# o gato é pequeno na rua não existe com o braço dele segurando o celular. Esses
# beats viram foto que ele tirou do lugar, e o roteirista é avisado.
#
# `camera` multiplica o movimento de câmera. Não é enfeite: a mesma amplitude de
# pan que respira num plano aberto vira tremor num macro do olho, porque no macro
# cada pixel de deslocamento é muito mais campo de visão. Escala e movimento têm
# que andar juntos ou um denuncia o outro.


@dataclass(frozen=True)
class Enquadramento:
    chave: str
    resumo: str  # PT, para o roteirista e para o log
    visual: str  # EN, para o gpt-image-2
    familia: str  # "fechado" | "medio" | "aberto"
    peso: float  # com que frequência ele aparece, dentro da família dele
    so_outros: bool = False
    camera: float = 1.0


ENQUADRAMENTOS = [
    Enquadramento(
        "olho",
        "macro extremo: um detalhe só preenchendo a tela — o olho, o focinho, a "
        "pata na parede morna, um pingo no bigode",
        "FRAMING — an extreme macro close-up. A single detail fills the entire "
        "frame edge to edge: the eye with the whole street reflected in it, the "
        "wet nose, a paw pad on warm stone, dew on a whisker. Everything else is "
        "far out of focus. The phone is a few centimetres away.",
        "fechado",
        peso=1.0,
        camera=0.35,
    ),
    Enquadramento(
        "close",
        "close no rosto: a cara preenchendo o quadro, o fundo desmanchado",
        "FRAMING — a tight close-up of the face. The head fills most of the "
        "frame, cropped at the ears and the chest, the background dissolved into "
        "soft bokeh. Shot from very near.",
        "fechado",
        peso=2.5,
        camera=0.6,
    ),
    Enquadramento(
        "medio",
        "plano médio: do peito para cima, um pedaço do lugar aparecendo atrás",
        "FRAMING — a medium shot, from the chest up, with a readable slice of the "
        "place behind him. Arm's length from the phone.",
        "medio",
        peso=3.5,
    ),
    Enquadramento(
        "corpo",
        "o gato inteiro no quadro, com o lugar legível em volta dele",
        "FRAMING — the whole cat in frame from nose to tail, with the place "
        "clearly readable around him. Taken from a couple of metres away.",
        "medio",
        peso=3.0,
    ),
    Enquadramento(
        "contra_plongee",
        "contra-plongée: o celular quase no chão, apontado para cima — ele grande "
        "contra o céu, com poste, laje e folhagem convergindo lá em cima",
        "FRAMING — a strong low-angle shot (contre-plongée). The phone is almost "
        "on the ground, tilted steeply upward. He looms large against the open "
        "sky; power lines, the edge of a rooftop slab, tree branches and a lamp "
        "post converge overhead. Heroic, slightly distorted by the wide lens.",
        "medio",
        peso=2.0,
        camera=0.8,
    ),
    Enquadramento(
        "de_cima",
        "de cima: o celular erguido bem acima da cabeça, apontado para baixo",
        "FRAMING — a high-angle shot from directly above, the phone held well "
        "over his head and pointed down. You see the top of his head, his back "
        "and the ground around him flattened out beneath.",
        "medio",
        peso=1.5,
        camera=0.8,
    ),
    Enquadramento(
        "aberto",
        "plano aberto do LUGAR: a rua e o bairro ocupando a tela, e quem estiver "
        "lá (o Black, outro gato, um vizinho) pequeno no meio",
        "FRAMING — a wide shot of the place. The street and the neighbourhood "
        "fill the frame: the pavement running away, the walls, the trees, the "
        "houses, the sky above the wires. Whoever is in it — the black cat, "
        "another cat, a neighbour — is small, in the middle distance. The place "
        "is the subject.",
        "aberto",
        peso=0.9,
        so_outros=True,
        camera=1.25,
    ),
    Enquadramento(
        "panorama",
        "panorâmica do alto: o bairro inteiro e o céu, e quem aparecer é minúsculo",
        "FRAMING — a very wide establishing shot taken from high up: from a "
        "rooftop slab, the top of a wall or the steps of an alley. Rooftops, "
        "treetops, the whole sky and the distant city skyline fill the frame. Any "
        "cat in it is tiny, almost lost in a corner.",
        "aberto",
        peso=0.5,
        so_outros=True,
        camera=1.4,
    ),
]

# Os três que o vídeo tem que ter, sempre. São as pontas da escala — sem o macro
# e sem o aberto no mesmo vídeo, não existe contraste para o corte marcar.
ENQUADRAMENTOS_OBRIGATORIOS = ("olho", "aberto", "contra_plongee")

# Com o que o beat 1 pode abrir. O gancho tem um segundo para a piada ser
# entendida, e piada de posição precisa do corpo inteiro e do lugar em volta:
# um macro do olho não conta que ele está dentro de uma caixa pequena demais.
ENQUADRAMENTOS_ABERTURA = ("corpo", "contra_plongee", "de_cima")


def _sortear_enquadramentos(
    rng: random.Random, total: int, teto_outros: int
) -> list[Enquadramento]:
    """Sorteia a escala de plano de cada foto, garantindo contraste em todo corte.

    Três garantias, e cada uma existe porque sem ela o sorteio devolve slideshow:

    1. a FAMÍLIA nunca se repete de uma foto para a seguinte. É a regra que faz o
       trabalho — dois planos médios diferentes seguidos ainda são duas fotos do
       mesmo tamanho;
    2. os três enquadramentos das pontas (macro, aberto, contra-plongée) aparecem
       pelo menos uma vez. Sorteio livre às vezes devolve dezesseis fotos entre
       médio e close, que é justamente a média de onde estamos saindo;
    3. os enquadramentos que não cabem numa selfie não passam do número de fotos
       "de outros" do dia, senão o roteiro receberia uma exigência impossível.

    A construção não tem tentativa e erro: os obrigatórios são colocados primeiro,
    em posições espalhadas, e o resto é preenchido da esquerda para a direita
    escolhendo entre os que não batem de família com os vizinhos já postos. Como
    são três famílias e a menor tem dois membros, sempre sobra candidato.
    """
    por_familia: dict[str, list[Enquadramento]] = {}
    for e in ENQUADRAMENTOS:
        por_familia.setdefault(e.familia, []).append(e)

    seq: list[Enquadramento | None] = [None] * total
    seq[0] = rng.choice([e for e in ENQUADRAMENTOS if e.chave in ENQUADRAMENTOS_ABERTURA])
    orcamento = teto_outros - (1 if seq[0].so_outros else 0)

    def cabe(e: Enquadramento, i: int) -> bool:
        if e.so_outros and orcamento <= 0:
            return False
        vizinhos = [seq[j] for j in (i - 1, i + 1) if 0 <= j < total and seq[j]]
        return all(e.familia != v.familia for v in vizinhos)

    # Os obrigatórios primeiro, um em cada terço do vídeo: espalhados, o contraste
    # aparece três vezes ao longo dos 31s em vez de tudo no mesmo trecho.
    obrigatorios = [e for e in ENQUADRAMENTOS if e.chave in ENQUADRAMENTOS_OBRIGATORIOS]
    rng.shuffle(obrigatorios)
    faixa = (total - 1) / len(obrigatorios)
    for n, e in enumerate(obrigatorios):
        posicoes = [
            i
            for i in range(1 + round(n * faixa), 1 + round((n + 1) * faixa))
            if i < total and seq[i] is None and cabe(e, i)
        ]
        if posicoes:
            i = rng.choice(posicoes)
            seq[i] = e
            orcamento -= e.so_outros

    for i in range(total):
        if seq[i] is not None:
            continue
        candidatos = [e for e in ENQUADRAMENTOS if cabe(e, i)]
        # Rede: se a vizinhança fechar todas as portas (só acontece se a tabela
        # de enquadramentos perder membros), vale qualquer família diferente da
        # anterior, e no limite qualquer um.
        candidatos = candidatos or [
            e for e in ENQUADRAMENTOS if not e.so_outros or orcamento > 0
        ] or list(ENQUADRAMENTOS)
        escolhido = rng.choices(candidatos, [e.peso for e in candidatos])[0]
        seq[i] = escolhido
        orcamento -= escolhido.so_outros

    return [e for e in seq if e is not None]


# ---- Movimento de câmera -----------------------------------------------------

# Amplitudes do zoom lento de cada foto, e o quanto do espaço disponível a
# câmera pode varrer. Suave de propósito: movimento que se percebe vira efeito,
# e o vídeo tem que continuar parecendo um story, não um trailer.
#
# As duas faixas são POR SEGUNDO, e não por foto. É o que importa quando as
# fotos deixam de ter todas a mesma duração: a mesma amplitude de zoom em 2s é o
# dobro da velocidade que era em 4s, e o dobro da velocidade é onde o Ken Burns
# para de parecer respiração e passa a parecer efeito. Multiplicando pela
# duração, a foto de 1s e a de 2s se movem no mesmo ritmo — só percorrem
# distâncias diferentes.
ZOOM_BASE = 1.08  # piso do zoom — precisa sobrar margem para o pan existir
ZOOM_TAXA = (0.015, 0.033)  # amplitude de zoom por segundo de foto
PAN_TAXA = (0.0, 0.19)  # fração da margem disponível varrida por segundo

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
    pan: float  # fração da margem varrida, já sorteada e já escalada pela duração


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
    gancho: str
    ancoras: dict[str, str]
    convidado: Personagem | None
    quantas_outros: int
    enquadramentos: list[Enquadramento] = field(default_factory=list)
    movimentos: list[Movimento] = field(default_factory=list)

    def resumo(self) -> str:
        """Uma linha por item sorteado, para o log da execução."""
        visita = self.convidado.chave if self.convidado else "ninguém (só os dois)"
        return "\n".join(
            f"  {rotulo}: {valor}"
            for rotulo, valor in (
                ("semente", self.semente),
                ("gancho", self.gancho),
                ("tempo", self.clima),
                ("época", self.calendario),
                ("humor", self.humor),
                ("rolê", self.forma),
                ("tempero", self.tempero),
                ("visita", visita),
                ("fotos de outros", str(self.quantas_outros)),
                ("escala", " ".join(e.chave for e in self.enquadramentos)),
            )
        )

    def indices_so_outros(self) -> list[int]:
        """Beats cujo enquadramento não cabe numa selfie de pata esticada."""
        return [i for i, e in enumerate(self.enquadramentos) if e.so_outros]


def _movimentos(
    rng: random.Random,
    duracoes: list[float],
    enquadramentos: list[Enquadramento],
) -> list[Movimento]:
    """Sorteia o movimento de cada foto, sem repetir o da anterior.

    A regra de não repetir é o ponto: dezesseis fotos com o mesmo zoom dão
    sensação de esteira transportadora, e é isso que denuncia que o vídeo é
    montado. Com o corte caindo a cada segundo e pouco, a repetição aparece
    numa frequência alta o bastante para ser reconhecida como padrão.

    A direção nova a cada corte também é o que marca a fronteira entre as fotos:
    a câmera recomeça visivelmente, em vez de dar a impressão de continuar.
    """
    movimentos: list[Movimento] = []
    fecha = rng.random() < 0.5
    anterior = None
    for duracao, enq in zip(duracoes, enquadramentos):
        # A amplitude é escalada pela duração E pela escala do plano. Pela
        # duração porque o movimento é uma taxa por segundo; pela escala porque
        # um mesmo deslocamento em pixels é uma fração muito maior do campo de
        # visão num macro do que num plano aberto — o pan que respira no aberto
        # é tremor no olho do gato.
        amplitude = rng.uniform(*ZOOM_TAXA) * duracao * enq.camera
        z_ini, z_fim = (
            (ZOOM_BASE, ZOOM_BASE + amplitude)
            if fecha
            else (ZOOM_BASE + amplitude, ZOOM_BASE)
        )
        opcoes = [d for d in DIRECOES if d != anterior]
        direcao = rng.choice(opcoes)
        anterior = direcao
        movimentos.append(
            Movimento(
                z_ini,
                z_fim,
                direcao[0],
                direcao[1],
                rng.uniform(*PAN_TAXA) * duracao * enq.camera,
            )
        )
        # Alterna a direção do zoom na maior parte das vezes, mas nem sempre:
        # alternância perfeita é um padrão, e padrão também fica previsível.
        fecha = not fecha if rng.random() < 0.75 else fecha
    return movimentos


def sortear(quando: datetime | None = None) -> Variacao:
    """Sorteia o dia de hoje. A semente é a data + a hora do run.

    Sai sem os movimentos de câmera de propósito: eles dependem da duração de
    cada foto, e a duração de cada foto só existe depois que o roteiro conta a
    história do dia (ver `sortear_movimentos`).
    """
    agora = quando or datetime.now()
    semente = agora.strftime("%Y-%m-%d-%H")
    rng = random.Random(semente)

    clima, clima_en = rng.choice(CLIMAS)
    convidado = rng.choice(ELENCO) if rng.random() < CHANCE_CONVIDADO else None
    quantas_outros = rng.randint(*FAIXA_OUTROS)

    return Variacao(
        semente=semente,
        clima=clima,
        clima_en=clima_en,
        calendario=CALENDARIO[agora.month],
        humor=rng.choice(HUMORES),
        forma=rng.choice(FORMAS),
        tempero=rng.choice(TEMPEROS),
        gancho=rng.choice(GANCHOS),
        ancoras={rotulo: rng.choice(opcoes) for rotulo, opcoes in ANCORAS.items()},
        convidado=convidado,
        quantas_outros=quantas_outros,
        enquadramentos=_sortear_enquadramentos(rng, TOTAL_IMAGENS, quantas_outros),
    )


def sortear_movimentos(var: Variacao, duracoes: list[float]) -> None:
    """Preenche os movimentos de câmera, já sabendo quanto dura cada foto.

    Recebe as durações, e não a quantidade de fotos, porque o movimento é
    sorteado em taxa POR SEGUNDO: com as fotos durando de 1s a 3,5s, a mesma
    amplitude de zoom seria três vezes mais rápida numa do que na outra — e
    velocidade de zoom é justamente o que separa respiração de efeito.

    O sorteio usa uma corrente própria (a semente do dia com um sufixo), e não a
    do `sortear`. É o que mantém o run reproduzível mesmo tendo sido partido em
    dois: o que o roteirista escreve entre uma chamada e outra não desloca mais
    nada.
    """
    var.movimentos = _movimentos(
        random.Random(f"{var.semente}-camera"), duracoes, var.enquadramentos
    )
