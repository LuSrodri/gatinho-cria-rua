"""O roteiro do dia, escrito pelo gpt-5.6-luna.

Uma execução = um dia na vida dele. A rotina é fixa (ver ``BEATS`` em
config.py) e o que o modelo inventa é o RECHEIO: o que exatamente ele vê, o que
o Black está aprontando, e a legenda de cada foto.

O modelo não escreve no vazio: ``variacao.sortear`` já decidiu, em Python, o
tempo que faz hoje, o humor dele, quem do bairro aparece e que forma o rolê tem.
Isso é de propósito — pedir variedade a um LLM devolve a média dele, que é o
lugar-comum. Com os parâmetros dados, ele gasta a criatividade no que sabe fazer
bem: o detalhe concreto e a frase curta.

Saem duas coisas por cena, em idiomas diferentes de propósito:

- ``cena``: descrição visual em INGLÊS, que vira prompt do gpt-image-2. Modelo
  de imagem entende inglês muito melhor, e o texto nunca aparece na tela.
- ``legenda``: o texto em PORTUGUÊS que vai queimado no vídeo, escrito na voz
  dele — story de Instagram, primeira pessoa, curto.
"""

import json
import random
from datetime import datetime

from openai import OpenAI

from .config import BEATS, BEATS_ROLE, Config
from .variacao import Variacao

# A legenda em palavras, não em caracteres. Contar palavra é o que dá para pedir
# a um modelo e ele cumprir; o teto de caracteres continua existindo, mas como
# rede de segurança do layout, não como a regra.
#
# De 3 a 6 palavras porque a foto fica 2s na tela e o corpo da fonte subiu para
# 76px (legendas.py): é o que cabe em duas linhas grandes e se lê num relance.
# Menos de 3 vira legenda-etiqueta ("café"), que não tem voz nenhuma.
MIN_PALAVRAS = 3
MAX_PALAVRAS = 6

# Quantas vezes pedir o roteiro antes de desistir do run (ver gerar_roteiro).
TENTATIVAS = 3

# Teto de caracteres. Seis palavras compridas ainda estouram duas linhas a 76px,
# e a legenda encolheria até deixar de competir com a foto.
MAX_LEGENDA = 44

# Sementes de rolê. Não entram no prompt como lista fechada de escolhas — entram
# como EXEMPLOS do nível de especificidade que se espera. Sem elas o modelo cai
# sempre no mesmo "eles andam pela rua e conversam".
EXEMPLOS_ROLE = [
    "o campinho de várzea com o refletor novo aceso",
    "a fila do trailer de pastel que abre de madrugada",
    "a laje de um amigo com caixa de som e churrasco",
    "o banco da praça arborizada onde a galera senta",
    "o ensaio da quadra da escola de samba",
    "a padaria da esquina que abre de madrugada",
    "o mirante no fim da rua sem saída, com a cidade acesa embaixo",
    "a oficina do tio que fica aberta até tarde",
    "a horta comunitária no terreno da esquina",
    "a escadaria com o mural novo que um artista pintou",
    "a feira sendo montada às três da manhã",
    "o pesqueiro improvisado do vizinho, na laje",
    "o sarau que acontece toda semana embaixo do viaduto",
    "a quadra iluminada onde rola futebol até tarde",
]

ESQUEMA = {
    "name": "dia_do_gatinho",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "titulo": {
                "type": "string",
                "description": (
                    "Título do Short em português, no máximo 80 caracteres, na voz "
                    "dele. Sem aspas. Deve terminar com ' #Shorts'."
                ),
            },
            "descricao": {
                "type": "string",
                "description": (
                    "Descrição do vídeo em português, 2 a 4 linhas, na voz dele, "
                    "intimista. Pode terminar com hashtags."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "8 a 12 tags em português, sem '#'.",
            },
            "cenas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        # `enum`, e não string livre. O modo estrito da OpenAI não
                        # aceita `minItems`/`maxItems`, então a QUANTIDADE de cenas
                        # não é exigível pelo schema — e um run de 16 beats já
                        # voltou com 17 cenas, abortando a execução. O que dá para
                        # exigir é o NOME de cada beat; com ele fechado, a lista
                        # vira reconciliável por nome em `_alinhar`, e a contagem
                        # deixa de importar.
                        "beat": {
                            "type": "string",
                            "enum": [nome for nome, _ in BEATS],
                        },
                        "foto": {
                            "type": "string",
                            "enum": ["selfie", "outros"],
                            "description": (
                                "'selfie' = ele com a pata esticada segurando o "
                                "celular. 'outros' = foto que ELE tirou de outros "
                                "gatos, ele não aparece."
                            ),
                        },
                        "cena": {
                            "type": "string",
                            "description": (
                                "ENGLISH. Visual description of this single photo: "
                                "who is in frame, what they are doing, where, and "
                                "the light. 2 to 4 sentences. No text, no words, no "
                                "captions in the image."
                            ),
                        },
                        "legenda": {
                            "type": "string",
                            "description": (
                                f"PORTUGUÊS. De {MIN_PALAVRAS} a {MAX_PALAVRAS} "
                                f"palavras, no máximo {MAX_LEGENDA} caracteres. A "
                                "legenda do story, na voz dele."
                            ),
                        },
                    },
                    "required": ["beat", "foto", "cena", "legenda"],
                },
            },
        },
        "required": ["titulo", "descricao", "tags", "cenas"],
    },
}

PERSONAGEM = """\
QUEM É ELE
Um gato laranja (orange tabby) de rua, magrinho, cara de moleque. Ele não fala e
não anda em duas patas: é um gato de verdade, com anatomia de gato. O que ele
faz é viver como um adolescente de 16-18 anos da periferia de São Paulo — toma
café, tem amigo, vai pro rolê, posta story. A graça está nesse contraste: um
gato comum fazendo coisa de moleque.

Ele dorme o dia inteiro e acorda no fim da tarde. Passa a noite na rua com o
Black e vai direto pra escola de manhã, sem dormir. Todo dia.

O BLACK
Gato preto, pelo curto e brilhante, olhos amarelos. Amigo dele. Simpático,
falante, sempre negociando alguma coisa com alguém. É o extrovertido da dupla.

O CELULAR
Todas as 16 imagens são fotos que ELE tirou com o celular e postou no story. Ou é
selfie (pata esticada, ângulo de baixo, meio torto, lente meio distorcida na
borda), ou é foto que ele tirou de OUTROS gatos — e essa é a parte que ele mais
gosta de compartilhar: dois gatos dividindo comida, o Black tentando negociar
alguma coisa com um gato desconhecido, um casal de gatos juntos num muro florido,
um gato velho dormindo no capô morno. Ele é o tipo que registra tudo.
"""

VOZ = f"""\
A VOZ DAS LEGENDAS
Primeira pessoa, português do Brasil, gíria de quebrada paulista de forma
natural (nunca caricata, nunca "mano do céu" forçado). Tudo em minúsculas, como
quem digita rápido no celular.

O TAMANHO É REGRA DURA: de {MIN_PALAVRAS} a {MAX_PALAVRAS} palavras, no máximo
{MAX_LEGENDA} caracteres. Não é preferência de estilo — a foto fica 2 segundos
na tela e a legenda é grande. Sete palavras não são lidas antes do corte, e o
que não é lido não existe. Corte artigo, corte explicação, corte a segunda
ideia. Uma legenda = um pensamento.

O tom é INTIMISTA. Não é comédia escancarada e não é frase de efeito
motivacional. É o pensamento solto de quem tá vivendo aquilo: meio sonolento,
meio observador, às vezes carinhoso, às vezes com uma melancolia leve que ele
não comenta. Ele repara nas coisas.

Pode usar emoji, no máximo um, e só quando faz falta. O emoji conta como palavra.

BOM ({MIN_PALAVRAS} a {MAX_PALAVRAS} palavras):   RUIM (comprido ou genérico):
"ja ta escurecendo"                   "acordei agora e ja ta escurecendo de novo"
"o black nunca perde uma"             "Meu amigo Black é muito engraçado kkkk"
"esses dois to shippando"             "Olha só que casal fofo de gatinhos!"
"ninguem avisou que amanheceu"        "A noite passou voando, que loucura!"
"vou dormir na aula"                  "Hora de ir para a escola estudar!"
"o portao ainda ta morno"             "O portão de casa ainda está morninho de sol"
"""

ESTETICA = """\
A ESTÉTICA (vale para todos os campos "cena")
Periferia de São Paulo, na versão BONITA e cuidada dela: rua arborizada com ipês
floridos, casinhas pintadas em cores quentes, muro baixo com planta caindo por
cima, jardim na frente, samambaia pendurada na varanda, laje com horta e varal,
calçada de pedra portuguesa, padaria de esquina com toldo, praça com quadra,
mural colorido pintado por artista do bairro. Continua sendo periferia — laje,
portão, grade, fio de poste cruzando o céu, escadaria de viela —, mas é o bairro
próspero, plantado e bem cuidado, e o skyline da cidade aparece longe entre os
telhados.

Nunca miséria, nunca entulho, nunca tijolo cru, nunca lixo, nunca favela
estereotipada de filme. A sensação de toda foto tem que ser paz, fartura e
pertencimento.

A luz é o personagem principal, e ela ANDA ao longo dos 16 beats — é o relógio
do vídeo. Cada faixa tem que ser inconfundível da anterior:

- beats 1 a 4: fim de tarde, sol baixo e dourado atravessando as folhas, sombras
  compridas, tudo cor de mel;
- beats 5 a 7: o anoitecer acontecendo, céu azul-violeta com um resto de laranja
  no horizonte, as primeiras luzes de poste e de janela acendendo;
- beats 8 a 11: noite quente e cheia, luz de poste âmbar, brilho da padaria,
  luzinha de varal, refletor de quadra, o céu já preto-azulado;
- beats 12 e 13: madrugada alta, luz fria e escassa, rua vazia, orvalho
  começando, o primeiro clarão cinza-azulado no fundo do céu;
- beats 14 a 16: nascer do sol, azul frio virando rosa e dourado, ar limpo,
  vapor subindo do asfalto, luz nova e horizontal.

Escreva "cena" em inglês, como quem descreve uma foto de celular: quem está no
quadro, fazendo o quê, onde, e como está a luz. Nunca peça texto, letras, placas
legíveis ou marcas na imagem.
"""


def _numerar(indices: tuple[int, ...]) -> str:
    """Índices de BEATS na numeração humana do prompt: (7, 8, 9, 10) -> '8, 9, 10 e 11'.

    O prompt fala em "beat 8" e o código em `BEATS[7]`. Deixar essa conversão em
    um lugar só é o que evita o erro clássico deste arquivo: mexer na lista de
    beats e esquecer de mexer no texto que aponta para eles.
    """
    numeros = [str(i + 1) for i in indices]
    return f"{', '.join(numeros[:-1])} e {numeros[-1]}" if len(numeros) > 1 else numeros[0]


BEATS_ANCORA = tuple(i for i in range(len(BEATS)) if i not in BEATS_ROLE)


def _contexto_recentes(recentes: list[dict]) -> str:
    """O que já foi publicado, para o rolê de hoje não repetir o de ontem."""
    if not recentes:
        return "Este é um dos primeiros vídeos do canal — não há histórico ainda."
    linhas = "\n".join(f"- {v.get('titulo', '')}" for v in recentes[:20] if v.get("titulo"))
    return (
        "JÁ PUBLICADO (os mais recentes primeiro). O rolê de hoje precisa ser "
        "claramente diferente destes — outro lugar, outra situação, outro "
        f"acontecimento:\n{linhas}"
    )


def _contexto_dia(var: Variacao) -> str:
    """Os parâmetros sorteados, entregues ao modelo como fatos, não como opções.

    Repare que nada aqui é "você pode escolher": é "hoje é assim". Dar escolha
    de volta ao modelo desfaz o sorteio, porque ele escolheria sempre a mesma
    coisa — a mais provável.
    """
    ancoras = "\n".join(f"- {rotulo}: {valor}" for rotulo, valor in var.ancoras.items())
    visita = (
        f"{var.convidado.chave} — {var.convidado.resumo}"
        if var.convidado
        else "ninguém. Hoje o rolê é só dos dois, e isso também é bom."
    )
    return f"""\
O DIA DE HOJE (não é sugestão: é o que está dado. Escreva EM CIMA disto.)

O tempo: {var.clima}. Vale para as 16 fotos — é um dia só.
A época do ano no bairro: {var.calendario}.
O humor dele hoje: {var.humor}.
O tempero do dia, o fio que atravessa as 16 fotos: {var.tempero}.
Quem do bairro aparece hoje: {visita}
A forma do rolê (beats {_numerar(BEATS_ROLE)}): {var.forma}.

O recheio dos beats-âncora de hoje:
{ancoras}

Use TODOS estes elementos, mas com mão leve: o tempero e a visita são
temperos mesmo — aparecem em uma ou duas fotos e são sentidos nas outras, nunca
explicados. O tempo e a época aparecem na luz e no cenário de todas as fotos.
{f'Escreva o nome "{var.convidado.chave}" nos campos "cena" em que essa pessoa aparecer.' if var.convidado else ''}"""


def _prompt(var: Variacao, recentes: list[dict]) -> str:
    agora = datetime.now()
    # A semente do sorteio também governa quais exemplos de rolê o modelo vê:
    # exemplo é âncora, e mudar a âncora todo run é metade da variedade.
    semente = random.Random(var.semente).sample(EXEMPLOS_ROLE, 3)
    roteiro_beats = "\n".join(
        f"{i + 1}. [{nome}] {desc}" for i, (nome, desc) in enumerate(BEATS)
    )
    selfies = len(BEATS) - var.quantas_outros
    return f"""\
Escreva o dia de hoje ({agora.strftime('%d/%m/%Y')}, {agora.strftime('%A')}) do
canal. São {len(BEATS)} fotos, exatamente uma por beat, na ordem abaixo.

{PERSONAGEM}

{VOZ}

OS {len(BEATS)} BEATS (obrigatórios, nesta ordem — use o nome do beat no campo "beat")
{roteiro_beats}

"cenas" tem EXATAMENTE {len(BEATS)} objetos, um por beat da lista acima, na
ordem acima. Nem {len(BEATS) - 1}, nem {len(BEATS) + 1}. Nenhum beat repetido,
nenhum beat de fora, nenhuma cena extra. Confira a contagem antes de responder.

Os beats {_numerar(BEATS_ANCORA)} são âncoras: a FUNÇÃO deles não muda, mas o
detalhe sim, e o detalhe de hoje já está definido abaixo.

Os beats {_numerar(BEATS_ROLE)} são o rolê de hoje. Escolha UM lugar e conte lá a
história de hoje, com começo, meio e fim ao longo dos quatro beats. Nível de
especificidade esperado (exemplos só para calibrar, não copie): {', '.join(semente)}.

O VÍDEO DÁ VOLTA. Ele reinicia sozinho, então o beat {len(BEATS)} não é o fim de
nada: a foto seguinte a ele é a do beat 1, ele acordando outra vez. Escreva a
última legenda como quem continua, não como quem se despede — nada de "até
amanhã", "boa noite", "foi isso", nem resumo do dia. O ciclo fecha porque
recomeça, e o espectador não pode receber aviso nenhum de que acabou.

{_contexto_dia(var)}

Exatamente {var.quantas_outros} das {len(BEATS)} fotos devem ser "outros" (foto
que ele tirou de outros), e {selfies} devem ser "selfie". O beat 1 é sempre
selfie. Não coloque duas fotos "outros" seguidas mais do que o necessário — com
o corte a cada 2s, alternar entre ele e o que ele vê é o que dá respiração.

{_contexto_recentes(recentes)}

{ESTETICA}"""


class _RoteiroInvalido(Exception):
    """O roteiro voltou fora do formato. Vale pedir outro, não vale abortar."""


def _alinhar(cenas: list[dict]) -> list[dict]:
    """Devolve exatamente uma cena por beat, na ordem de BEATS.

    A quantidade de cenas é a única parte do formato que o schema não consegue
    exigir (o modo estrito não tem `minItems`/`maxItems`), e com 16 beats o
    modelo erra a conta de vez em quando — o primeiro run com o formato novo
    voltou com 17. Como o nome do beat é `enum`, dá para reconstruir a lista por
    nome em vez de confiar na ordem e no comprimento: cena a mais é descartada,
    cena fora de ordem volta para o lugar, e beat repetido fica com a primeira
    ocorrência (a segunda costuma ser a improvisada).

    O que NÃO dá para consertar aqui é beat faltando: inventar uma cena para
    tapar o buraco produziria uma foto que não pertence ao dia. Aí é caso de
    pedir outro roteiro.
    """
    por_beat: dict[str, dict] = {}
    for cena in cenas:
        nome = (cena.get("beat") or "").strip().lower()
        if nome and nome not in por_beat:
            por_beat[nome] = cena

    faltando = [nome for nome, _ in BEATS if nome not in por_beat]
    if faltando:
        raise _RoteiroInvalido(
            f"vieram {len(cenas)} cenas e faltou o beat: {', '.join(faltando)}"
        )

    alinhadas = [por_beat[nome] for nome, _ in BEATS]
    if len(cenas) != len(alinhadas):
        print(
            f"[roteiro] O modelo devolveu {len(cenas)} cenas para {len(BEATS)} "
            "beats; realinhado pelo nome do beat."
        )
    return alinhadas


def gerar_roteiro(cfg: Config, var: Variacao, recentes: list[dict]) -> dict:
    """Devolve o roteiro do dia já validado (16 cenas, legendas no tamanho)."""
    print("[roteiro] Escrevendo o dia de hoje...")
    print(var.resumo())
    cliente = OpenAI(api_key=cfg.openai_api_key)

    # Vale a pena repetir a chamada: o roteiro é a etapa BARATA da execução (uma
    # chamada de texto contra 16 de imagem), e ele é o que decide se as outras
    # acontecem. Desistir na primeira resposta torta é perder o run inteiro —
    # e o cron só volta daqui a algumas horas.
    for tentativa in range(1, TENTATIVAS + 1):
        resposta = cliente.chat.completions.create(
            model=cfg.text_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você escreve um canal de Shorts em português do Brasil sobre "
                        "um gato de rua adolescente da periferia paulista. Você é bom "
                        "em observar o pequeno detalhe que faz a cena parecer real. "
                        "Você nunca escreve legenda genérica."
                    ),
                },
                {"role": "user", "content": _prompt(var, recentes)},
            ],
            response_format={"type": "json_schema", "json_schema": ESQUEMA},
        )
        roteiro = json.loads(resposta.choices[0].message.content)
        try:
            cenas = _alinhar(roteiro.get("cenas") or [])
            break
        except _RoteiroInvalido as erro:
            if tentativa == TENTATIVAS:
                raise SystemExit(
                    f"O roteiro veio fora do formato {TENTATIVAS} vezes ({erro}). "
                    "Abortando antes de gastar imagem."
                ) from erro
            print(f"[roteiro] Roteiro fora do formato ({erro}); pedindo outro.")

    roteiro["cenas"] = cenas

    # Legenda estourada é falha de layout, não de conteúdo: cortar aqui é melhor
    # do que deixar a caixa de story cobrir metade da foto. O corte é sempre em
    # palavra inteira, nos dois limites — legenda terminada no meio de uma
    # palavra é pior do que legenda comprida.
    for cena in cenas:
        legenda = (cena.get("legenda") or "").strip()
        curta = " ".join(legenda.split()[:MAX_PALAVRAS])
        if len(curta) > MAX_LEGENDA:
            curta = curta[:MAX_LEGENDA].rsplit(" ", 1)[0]
        curta = curta.rstrip(",.;:- ")
        if curta != legenda:
            cena["legenda"] = curta
            print(f"[roteiro] Legenda cortada: {legenda!r} -> {curta!r}")

    print(f"[roteiro] '{roteiro.get('titulo', '')}' — {len(cenas)} cenas.")
    return roteiro
