"""O roteiro do dia, escrito pelo gpt-5.6-luna.

Uma execução = um dia na vida dele. A rotina é fixa (ver ``BEATS`` em
config.py) e o que o modelo inventa é o RECHEIO: o que exatamente ele vê, o que
o Black está aprontando, e a legenda de cada foto.

O modelo não escreve no vazio: ``variacao.sortear`` já decidiu, em Python, o
tempo que faz hoje, o humor dele, quem do bairro aparece e que forma o rolê tem.
Isso é de propósito — pedir variedade a um LLM devolve a média dele, que é o
lugar-comum. Com os parâmetros dados, ele gasta a criatividade no que sabe fazer
bem: o detalhe concreto e a frase curta.

Saem três coisas por cena, e as duas primeiras em idiomas diferentes de
propósito:

- ``cena``: descrição visual em INGLÊS, que vira prompt do gpt-image-2. Modelo
  de imagem entende inglês muito melhor, e o texto nunca aparece na tela.
- ``legenda``: o texto em PORTUGUÊS que vai queimado no vídeo, escrito na voz
  dele — story de Instagram, primeira pessoa, curto.
- ``ritmo``: quanto tempo a foto fica na tela. É a única decisão do roteirista
  que sai do conteúdo e entra na MONTAGEM, e ela cresceu: além de decidir cada
  corte, a soma dos oito ritmos é agora a DURAÇÃO DO VÍDEO, que deixou de ser
  fixa em 31s (ver `montar_ritmo` em config.py).

O que ele NÃO escolhe é a escala de plano: ela é sorteada em variacao.py, com a
regra de nunca repetir a família de um corte para o outro, e chega aqui como
fato. O roteirista escreve a cena PARA o enquadramento que recebeu — o que muda
bastante o que ele escreve, porque num macro do olho não cabe uma travessia de
rua e num plano aberto não cabe uma expressão de cara.
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
# De 3 a 6 palavras porque a foto mais curta fica pouco mais de um segundo na
# tela e o corpo da fonte é grande (89px, legendas.py): é o que cabe em uma ou
# duas linhas e se lê num relance. Menos de 3 vira legenda-etiqueta ("café"),
# que não tem voz nenhuma.
MIN_PALAVRAS = 3
MAX_PALAVRAS = 6

# Quantas vezes pedir o roteiro antes de desistir do run (ver gerar_roteiro).
TENTATIVAS = 3

# Teto de caracteres, e ele DESCEU de 44 para 36 quando a fonte subiu de 76 para
# 89px. São a mesma decisão: a linha da legenda tem ~970px úteis, o que a 89px dá
# umas 20 letras. 44 caracteres não cabiam em duas linhas nesse corpo — cabiam em
# três, ou faziam a legenda encolher de volta para o tamanho de onde tinha saído.
# Encurtar a frase é o que deixa a fonte crescer de verdade.
MAX_LEGENDA = 36

# Quantos segundos cada ritmo dura na tela. O roteirista devolve o NOME do ritmo
# — é o que um modelo cumpre com precisão, enquanto pedir segundos devolve
# números que não somam nada — e `config.montar_ritmo` converte para quadros.
#
# Estes números deixaram de ser uma pretensão e passaram a ser a duração de
# verdade quando o total do vídeo parou de ser fixo: não há mais orçamento para
# encaixar, então o que a cena pede é o que ela leva, e a soma é o tamanho do
# Short. Continuam sendo durações, e não pesos abstratos, porque agora a média
# delas é literalmente o comprimento do vídeo: oito fotos nesta tabela dão de 11s
# (tudo corrida) a 24s (tudo longa), e uns 16s na distribuição comum.
#
# A distância entre "corrida" e "longa" é grande de propósito: se marcar uma cena
# como longa a alonga em meio segundo, ninguém vê diferença nenhuma e o vídeo
# continua com cara de metrônomo.
RITMOS = {
    "corrida": 1.4,
    "normal": 1.95,
    "demorada": 2.6,
    "longa": 3.4,
}

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
                        # não é exigível pelo schema — e na época dos dezesseis
                        # beats um run voltou com 17 cenas, abortando a
                        # execução. O que dá para
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
                        "ritmo": {
                            "type": "string",
                            "enum": list(RITMOS),
                            "description": (
                                "Quanto esta foto pede de tempo na tela. "
                                "'corrida' = foto de passagem, o olho pega de "
                                "relance; 'normal' = o padrão; 'demorada' = tem "
                                "detalhe ou emoção para ver; 'longa' = é o momento "
                                "da história, precisa respirar. Poucas 'longa'."
                            ),
                        },
                    },
                    "required": ["beat", "foto", "cena", "legenda", "ritmo"],
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
Todas as fotos do story foram tiradas por ELE com o celular. Ou é selfie (pata
esticada, ângulo de baixo, meio torto, lente meio distorcida na
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
{MAX_LEGENDA} caracteres. Não é preferência de estilo — a foto pode ficar só um
segundo e pouco na tela e a legenda é grande. Sete palavras não são lidas antes
do corte, e o que não é lido não existe. Corte artigo, corte explicação, corte a
segunda ideia. Uma legenda = um pensamento.

Frase curta cabe em UMA linha, e uma linha só é o que se lê de relance. Duas
linhas o vídeo aguenta; três, não. Na dúvida entre duas palavras e uma, escreva
uma.

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

A luz é o personagem principal, e ela ANDA ao longo dos 8 beats — é o relógio do
vídeo. São oito fotos para atravessar a tarde inteira até o dia seguinte, então
cada beat pula uma hora de verdade e tem que ser INCONFUNDÍVEL do anterior. Duas
fotos com a mesma luz, aqui, param o relógio:

- beat 1: fim de tarde, sol baixo e dourado atravessando as folhas, sombras
  compridas, tudo cor de mel;
- beat 2: o mesmo fim de tarde já mais baixo, o sol raspando os telhados, a luz
  ficando laranja e a sombra tomando a rua;
- beat 3: o anoitecer acontecendo, céu azul-violeta com um resto de laranja no
  horizonte, as primeiras luzes de poste e de janela acendendo;
- beats 4 a 6: noite quente e cheia, luz de poste âmbar, brilho da padaria,
  luzinha de varal, refletor de quadra, o céu já preto-azulado. Dentro do rolê a
  noite também anda: o beat 6 é mais tarde e mais quieto que o beat 4;
- beat 7: madrugada alta, luz fria e escassa, rua vazia, orvalho começando, o
  primeiro clarão cinza-azulado no fundo do céu;
- beat 8: nascer do sol, azul frio virando rosa e dourado, ar limpo, vapor
  subindo do asfalto, luz nova e horizontal.

Escreva "cena" em inglês, como quem descreve uma foto de celular: quem está no
quadro, fazendo o quê, onde, e como está a luz. Nunca peça texto, letras, placas
legíveis ou marcas na imagem.
"""


RITMO = f"""\
O RITMO (campo "ritmo" de cada cena)
O vídeo não corta em intervalo fixo: cada foto fica na tela o tempo que a
história pede, entre 1,3 e 3,5 segundos. Você decide isso cena a cena, e é o que
transforma oito fotos numa narrativa em vez de uma sequência.

A SOMA DO QUE VOCÊ ESCOLHER É A DURAÇÃO DO VÍDEO. Não existe tempo total a
respeitar: o dia de fotos rápidas fecha em uns doze segundos e o dia que respira
passa de vinte, e os dois são vídeos válidos. O que não é válido é marcar tudo
como "longa" achando que tempo de tela é importância — oito fotos longas não dão
um vídeo importante, dão um vídeo lento.

- "corrida": foto de passagem. O olho pega de relance e segue. Deslocamento,
  caminho, chegada — o que só existe para levar de um lugar ao outro.
- "normal": o padrão. Uma coisa acontecendo, sem peso especial.
- "demorada": tem detalhe para ver, ou a legenda muda alguma coisa. O espectador
  precisa de um instante a mais.
- "longa": é O momento. O que aconteceu de melhor no rolê, a foto que ele
  postaria com orgulho, o nascer do sol. UMA no vídeo, no máximo duas — em oito
  fotos, a terceira "longa" já é um terço do vídeo parado, e se tudo é longo,
  nada é.

Alterne. Duas "corrida" seguidas antes de uma "demorada" é o que faz a
"demorada" pesar. Uma sequência inteira de "normal" devolve o metrônomo que
estamos tentando tirar. Distribua o peso pela história: o rolê é onde estão as
longas, a rotina é onde estão as corridas.

O beat 1 é exceção e não conta: ele tem 1 segundo cravado, sempre, seja qual for
o ritmo que você escrever nele.
"""


def _gancho(var: Variacao) -> str:
    """O bloco do gancho: a primeira foto tem uma função só dela."""
    return f"""\
O GANCHO (beat 1) — a parte mais importante do vídeo
A primeira foto tem UM SEGUNDO para impedir a pessoa de rolar o feed, e o público
é dono de gato. O que faz essa pessoa parar não é foto bonita de gato: é
reconhecer o próprio gato. O comentário que se quer embaixo do vídeo é
literalmente "MEU GATO FARIA ISSO KKKK".

A situação de hoje já está escolhida, e é esta:
>>> {var.gancho} <<<

Escreva o campo "cena" do beat 1 descrevendo ESSA foto, em inglês, com o absurdo
bem visível e imediato — o enquadramento tem que entregar a piada sozinho, sem a
legenda ajudar. Continua sendo selfie de celular tirada por ele, e ele continua
sendo um gato de verdade com anatomia de gato: nada de gato em pé, nada de gato
segurando coisa com a mão. É a POSIÇÃO e o LUGAR que são absurdos, não o gato.

A legenda do beat 1 é a reação dele à própria situação, e ela funciona como
legenda de dono de gato postando o gato: sem explicar o que a foto já mostra, com
a cara de pau ou o constrangimento de quem foi pego. Nada de "acordei" e nada de
"bom dia" — descrever que ele acordou é a informação mais óbvia e mais inútil que
essa foto tem.

O beat 2 continua de dentro dessa mesma situação: ele ainda está ali, saindo dela
devagar, já com o café. Depois disso o dia segue normal.
"""


ESCALA = """\
A ESCALA DE PLANO (já decidida — está na lista dos beats, uma por foto)
Cada foto tem um enquadramento dado: macro no olho, plano médio, contra-plongée,
plano aberto. Não é sugestão e não é sua escolha: escreva o campo "cena" PARA
aquele enquadramento, descrevendo o que aparece no quadro naquela distância e
naquele ângulo.

Isso muda o que você escreve, e é o ponto. Num macro do olho não cabe "ele
atravessa a rua": cabe o reflexo da rua inteira no olho dele. Num plano aberto
não cabe a expressão da cara dele: cabe a rua, a hora do dia, os dois pequenos no
meio de tudo. Um enquadramento fechado pede um detalhe; um aberto pede um lugar.

A foto tem que funcionar naquela escala — não descreva algo que só se veria em
outra."""


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

O tempo: {var.clima}. Vale para as {len(BEATS)} fotos — é um dia só.
A época do ano no bairro: {var.calendario}.
O humor dele hoje: {var.humor}.
O tempero do dia, o fio que atravessa as {len(BEATS)} fotos: {var.tempero}.
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
        f"{i + 1}. [{nome}] {desc}\n"
        f"    ENQUADRAMENTO: {var.enquadramentos[i].resumo}"
        + (" — nessa distância a pata dele não alcança o celular, então esta é "
           "obrigatoriamente foto de OUTROS: ELE NÃO ESTÁ NO QUADRO. Escreva o "
           "beat pelo lado do que ele está vendo, não pelo lado dele."
           if var.enquadramentos[i].so_outros else "")
        for i, (nome, desc) in enumerate(BEATS)
    )
    selfies = len(BEATS) - var.quantas_outros
    forcadas = var.indices_so_outros()
    # O arco, quando existe, entra logo depois das instruções do rolê: ele
    # substitui a forma sorteada, e uma instrução que substitui outra precisa vir
    # perto do que está substituindo para o modelo não escrever as duas.
    arco = f"\n{var.arco.instrucao}\n" if var.arco else ""
    return f"""\
Escreva o dia de hoje ({agora.strftime('%d/%m/%Y')}, {agora.strftime('%A')}) do
canal. São {len(BEATS)} fotos, exatamente uma por beat, na ordem abaixo.

{PERSONAGEM}

{VOZ}

{_gancho(var)}

{RITMO}

{ESCALA}

OS {len(BEATS)} BEATS (obrigatórios, nesta ordem — use o nome do beat no campo "beat")
{roteiro_beats}

"cenas" tem EXATAMENTE {len(BEATS)} objetos, um por beat da lista acima, na
ordem acima. Nem {len(BEATS) - 1}, nem {len(BEATS) + 1}. Nenhum beat repetido,
nenhum beat de fora, nenhuma cena extra. Confira a contagem antes de responder.

Os beats {_numerar(BEATS_ANCORA)} são âncoras: a FUNÇÃO deles não muda, mas o
detalhe sim, e o detalhe de hoje já está definido abaixo.

Os beats {_numerar(BEATS_ROLE)} são o rolê de hoje. Escolha UM lugar e conte lá a
história de hoje, com começo, meio e fim ao longo dos três beats. Nível de
especificidade esperado (exemplos só para calibrar, não copie): {', '.join(semente)}.
{arco}

O VÍDEO DÁ VOLTA. Ele reinicia sozinho, então o beat {len(BEATS)} não é o fim de
nada: a foto seguinte a ele é a do beat 1, ele acordando outra vez. Escreva a
última legenda como quem continua, não como quem se despede — nada de "até
amanhã", "boa noite", "foi isso", nem resumo do dia. O ciclo fecha porque
recomeça, e o espectador não pode receber aviso nenhum de que acabou.

{_contexto_dia(var)}

Exatamente {var.quantas_outros} das {len(BEATS)} fotos devem ser "outros" (foto
que ele tirou, sem ele no quadro), e {selfies} devem ser "selfie". O beat 1 é
sempre selfie. Os beats {_numerar(tuple(forcadas)) if forcadas else '(nenhum)'}
já contam entre as "outros", porque o enquadramento deles não cabe numa selfie.
Não coloque duas fotos "outros" seguidas mais do que o necessário — com o corte
caindo a cada segundo e pouco, alternar entre ele e o que ele vê é o que dá
respiração.

{_contexto_recentes(recentes)}

{ESTETICA}"""


class _RoteiroInvalido(Exception):
    """O roteiro voltou fora do formato. Vale pedir outro, não vale abortar."""


def _alinhar(cenas: list[dict]) -> list[dict]:
    """Devolve exatamente uma cena por beat, na ordem de BEATS.

    A quantidade de cenas é a única parte do formato que o schema não consegue
    exigir (o modo estrito não tem `minItems`/`maxItems`), e o modelo erra a
    conta de vez em quando — na época dos dezesseis beats um run voltou com
    dezessete. Com oito a conta é mais fácil e o erro deve ficar mais raro, mas
    "mais raro" não é "não acontece", e quatro runs por dia encontram o caso.
    Como o nome do beat é `enum`, dá para reconstruir a lista por nome em vez de
    confiar na ordem e no comprimento: cena a mais é descartada, cena fora de
    ordem volta para o lugar, e beat repetido fica com a primeira ocorrência (a
    segunda costuma ser a improvisada).

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
    """Devolve o roteiro do dia já validado (uma cena por beat, legendas no tamanho)."""
    print("[roteiro] Escrevendo o dia de hoje...")
    print(var.resumo())
    cliente = OpenAI(api_key=cfg.openai_api_key)

    # Vale a pena repetir a chamada: o roteiro é a etapa BARATA da execução (uma
    # chamada de texto contra oito de imagem), e ele é o que decide se as outras
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

    # O enquadramento manda no tipo de foto, não o contrário. Um plano em que o
    # gato é pequeno na rua não existe com a pata dele segurando o celular, e o
    # prompt já avisa quais beats são esses — mas avisar não é garantir, e uma
    # selfie pedida num plano aberto sai como um gato gigante flutuando sobre o
    # bairro. Corrigir aqui é uma linha; descobrir depois custa uma imagem.
    for i in var.indices_so_outros():
        if cenas[i].get("foto") != "outros":
            cenas[i]["foto"] = "outros"
            print(
                f"[roteiro] Beat {i + 1} ({BEATS[i][0]}) veio como selfie e o "
                f"enquadramento é '{var.enquadramentos[i].chave}'; virou foto de outros."
            )

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


def duracoes_pretendidas(roteiro: dict) -> list[float]:
    """Traduz o ritmo escrito em cada cena para os segundos que ela pretende durar.

    Ritmo ausente ou desconhecido vira "normal" em vez de derrubar a execução: o
    ritmo é uma melhora do vídeo, não um requisito dele, e um Short com uma cena
    no tempo padrão continua sendo um Short. O schema já exige o campo — isto
    aqui é a rede para o dia em que ele mudar.
    """
    return [
        RITMOS.get((cena.get("ritmo") or "").strip().lower(), RITMOS["normal"])
        for cena in roteiro["cenas"]
    ]
