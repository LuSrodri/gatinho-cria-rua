"""O roteiro do dia, escrito pelo gpt-5.6-luna.

Uma execução = um dia na vida dele. A rotina é fixa (ver ``BEATS`` em
config.py) e o que o modelo inventa é o RECHEIO: o que exatamente ele vê, o que
o Black está aprontando, e a legenda de cada foto.

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

from .config import BEATS, Config

# Teto de caracteres da legenda. Não é estética: é o que cabe em duas linhas na
# caixa de story sem virar parede de texto nos 2,5s que a imagem fica na tela.
MAX_LEGENDA = 64

# Sementes de rolê. Não entram no prompt como lista fechada de escolhas — entram
# como EXEMPLOS do nível de especificidade que se espera. Sem elas o modelo cai
# sempre no mesmo "eles andam pela rua e conversam".
EXEMPLOS_ROLE = [
    "um campinho de várzea com o refletor queimado",
    "a fila do trailer de pastel que abre de madrugada",
    "a laje de um amigo com caixa de som",
    "o ponto de ônibus vazio onde a galera senta",
    "a quadra da escola de samba ensaiando",
    "a padaria 24h com a luz branca dura",
    "o mirante improvisado no fim da rua sem saída",
    "a oficina do tio que fica aberta até tarde",
    "a lan house que ainda não fechou",
    "o corredor de escada da viela com grafite novo",
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
                        "beat": {"type": "string"},
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
                                f"PORTUGUÊS. Máximo {MAX_LEGENDA} caracteres. A "
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
Todas as 8 imagens são fotos que ELE tirou com o celular e postou no story. Ou é
selfie (pata esticada, ângulo de baixo, meio torto, lente meio distorcida na
borda), ou é foto que ele tirou de OUTROS gatos — e essa é a parte que ele mais
gosta de compartilhar: dois gatos brigando por comida, o Black tentando negociar
alguma coisa com um gato desconhecido, um casal de gatos juntos num muro, um
gato velho dormindo em cima do carro. Ele é o tipo que registra tudo.
"""

VOZ = f"""\
A VOZ DAS LEGENDAS
Primeira pessoa, português do Brasil, gíria de quebrada paulista de forma
natural (nunca caricata, nunca "mano do céu" forçado). Tudo em minúsculas, como
quem digita rápido no celular. No máximo {MAX_LEGENDA} caracteres.

O tom é INTIMISTA. Não é comédia escancarada e não é frase de efeito
motivacional. É o pensamento solto de quem tá vivendo aquilo: meio sonolento,
meio observador, às vezes carinhoso, às vezes com uma melancolia leve que ele
não comenta. Ele repara nas coisas.

Pode usar emoji, no máximo um, e só quando faz falta.

BOM:            RUIM:
"acordei agora, ja ta escurecendo"    "Bom dia! Que dia lindo hoje!"
"o black nunca perde uma"             "Meu amigo Black é muito engraçado kkkk"
"esses dois to shippando"             "Olha só que casal fofo de gatinhos!"
"ninguem me avisou que ja era manha"  "A noite passou voando, que loucura!"
"vou dormir na aula de novo"          "Hora de ir para a escola estudar!"
"""


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


def _prompt(recentes: list[dict]) -> str:
    agora = datetime.now()
    semente = random.sample(EXEMPLOS_ROLE, 3)
    roteiro_beats = "\n".join(
        f"{i + 1}. [{nome}] {desc}" for i, (nome, desc) in enumerate(BEATS)
    )
    return f"""\
Escreva o dia de hoje ({agora.strftime('%d/%m/%Y')}, {agora.strftime('%A')}) do
canal. São 8 fotos, exatamente uma por beat, na ordem abaixo.

{PERSONAGEM}

{VOZ}

OS 8 BEATS (obrigatórios, nesta ordem — use o nome do beat no campo "beat")
{roteiro_beats}

Os beats 1, 2, 3, 7 e 8 são âncoras: a FUNÇÃO deles não muda, mas o detalhe sim
(onde ele acordou, o que tem junto do café, como ele chama o Black, de onde ele
vê o nascer do sol, qual busão).

Os beats 4, 5 e 6 são o rolê de hoje, e é aí que mora a variedade. Escolha UM
lugar e conte uma coisa que acontece lá, com começo, meio e fim ao longo dos
três beats. Nível de especificidade esperado (exemplos só para calibrar, não
copie): {', '.join(semente)}.

Pelo menos 3 das 8 fotos devem ser "outros" (foto que ele tirou de outros
gatos). O beat 1 é sempre selfie.

{_contexto_recentes(recentes)}

A ESTÉTICA (vale para todos os campos "cena")
Periferia de São Paulo: casas de tijolo sem reboco, lajes, fios de poste
cruzando o céu, muros pichados, vielas, escadarias, grades. Nunca favela
estereotipada de filme — é o bairro comum, vivido e caseiro.

A luz é o personagem principal. Beats 1 a 3: fim de tarde, sol baixo e dourado.
Beats 4 a 6: noite, luz de poste amarela, néon de padaria, escuro quente.
Beats 7 e 8: nascer do sol, azul frio virando dourado.

Escreva "cena" em inglês, como quem descreve uma foto de celular: quem está no
quadro, fazendo o quê, onde, e como está a luz. Nunca peça texto, letras,
placas legíveis ou marcas na imagem.
"""


def gerar_roteiro(cfg: Config, recentes: list[dict]) -> dict:
    """Devolve o roteiro do dia já validado (8 cenas, legendas no tamanho)."""
    print("[roteiro] Escrevendo o dia de hoje...")
    cliente = OpenAI(api_key=cfg.openai_api_key)
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
            {"role": "user", "content": _prompt(recentes)},
        ],
        response_format={"type": "json_schema", "json_schema": ESQUEMA},
    )
    roteiro = json.loads(resposta.choices[0].message.content)

    cenas = roteiro.get("cenas") or []
    if len(cenas) != len(BEATS):
        raise SystemExit(
            f"O roteiro veio com {len(cenas)} cenas, e o formato exige "
            f"{len(BEATS)}. Abortando antes de gastar imagem."
        )

    # Legenda estourada é falha de layout, não de conteúdo: cortar aqui é melhor
    # do que deixar a caixa de story cobrir metade da foto.
    for cena in cenas:
        legenda = (cena.get("legenda") or "").strip()
        if len(legenda) > MAX_LEGENDA:
            cena["legenda"] = legenda[:MAX_LEGENDA].rsplit(" ", 1)[0].rstrip(",.;")
            print(f"[roteiro] Legenda cortada: {legenda!r} -> {cena['legenda']!r}")

    print(f"[roteiro] '{roteiro.get('titulo', '')}' — {len(cenas)} cenas.")
    return roteiro
