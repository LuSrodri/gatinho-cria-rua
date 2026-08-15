"""As 16 fotos do story, geradas pelo gpt-image-2.

O problema difícil aqui não é fazer imagem bonita: é fazer o MESMO gato dezesseis
vezes. Um canal de personagem morre no instante em que o espectador percebe que
o gato de cada foto é um gato diferente — e dobrar o número de fotos dobra as
chances de ele perceber.

A solução é ``images.edit`` com imagem de referência (o gpt-image-2 aceita uma
lista delas e processa todas em alta fidelidade). Duas classes de referência
circulam:

- ``assets/estetica.png``, commitada no repo: define o gato laranja e a estética
  do canal. Vai em TODAS as chamadas.
- Os coadjuvantes (o Black e o convidado do dia), que não têm referência
  commitada. A primeira foto em que cada um aparece é gerada ANTES das outras e
  vira a referência dele no resto da execução.

Por isso a geração é em duas ondas: primeiro as fotos que apresentam os
coadjuvantes, depois todas as outras em paralelo.
"""

import base64
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from .config import BEATS, Config
from .variacao import Variacao

TENTATIVAS = 3

# O que nunca muda de foto para foto. É o contrato visual do canal.
#
# Duas decisões que valem explicar, porque o instinto é fazer o contrário:
#
# 1. O CELULAR É BOM. A versão anterior pedia "cheap smartphone, sensor noise,
#    motion blur" atrás de autenticidade, e o que chegava era foto feia — ruído,
#    foco mole, cor lavada. Autenticidade vem do ENQUADRAMENTO (torto, na
#    correria, de baixo), não da qualidade ruim. Celular bom + mão de amador é a
#    combinação que dá foto de story bonita.
#
# 2. O BAIRRO É BONITO. Não é condomínio e não é centro: é o bairro residencial
#    arborizado de periferia paulista, com casa pintada, jardim na frente,
#    ipê na calçada e mural colorido no muro. Continua sendo periferia — laje,
#    portão, fio de poste, grade —, só que a versão cuidada dela, que é a que a
#    maior parte dela realmente é.
ESTILO = """\
STYLE — a photo taken on a good modern smartphone and posted to an Instagram
story. Photorealistic, sharp, well exposed, rich but natural colour. Shallow
depth of field with soft creamy bokeh in the background, gentle lens flare when
shooting toward the light, fine natural film grain. Beautiful light above
everything else: golden hour glow, warm rim light on fur, soft bloom around
lamps. Handheld and casual — slightly tilted horizon, imperfect framing, taken
quickly — but never blurry, never noisy, never dull. Think a very good amateur
photograph, warm and inviting, the kind people screenshot.

SETTING — a leafy, well-kept residential neighbourhood on the outskirts of São
Paulo, Brazil. Small painted houses in warm colours (ochre, mint, terracotta,
sky blue), low garden walls with plants spilling over them, front gardens,
potted ferns and flowers hanging from balconies, portuguese-stone pavements,
flowering ipê trees lining the street, a rooftop slab with a vegetable garden
and clean laundry on the line, a corner bakery with an awning and a table
outside, a tidy neighbourhood square with a court and mango trees, colourful
painted murals by local artists on the walls (art, never tags), a distant city
skyline visible between the rooftops. Power lines still cross the sky and there
are still window grilles and steep stepped alleys — this is the periphery, just
the cared-for, prosperous, planted version of it.

MOOD — peace, warmth, abundance, belonging. Everything looks loved and looked
after. Never poverty, never rubble, never bare unrendered brick, never rubbish,
never decay, never a movie-set slum.

ABSOLUTELY NO TEXT anywhere in the image: no words, no letters, no numbers, no
signage, no logos, no watermarks, no user interface, no caption bars."""

GATO = """\
THE MAIN CAT — a young orange tabby street cat, lean and healthy, with a soft
well-kept coat, expressive amber-green eyes and a young, cheeky face. He is a
REAL cat with normal cat anatomy: four legs, no clothes, never standing upright
like a human, never humanoid. He simply lives like a teenage boy would. Match
the cat in the reference image exactly: same fur pattern, same face, same
build."""

BLACK = """\
THE BLACK CAT — his friend "Black": a short-haired solid black cat with a glossy
coat and bright yellow eyes, friendly and talkative-looking, a bit stockier than
the orange cat. Also a REAL cat with normal cat anatomy."""

SELFIE = """\
SHOT TYPE — a front-camera selfie taken by the orange cat himself. One front paw
is stretched toward the camera holding the phone, so it is large and slightly
soft in the foreground. Low angle, tilted, close to his face, wide-angle
distortion at the edges. He is looking into the lens."""

OUTROS = """\
SHOT TYPE — a photo the orange cat took of other cats. He is NOT in the frame at
all. Candid, taken from a short distance, slightly crooked framing, as if he
raised the phone quickly to capture the moment."""


def _clima(var: Variacao) -> str:
    """A condição do dia, igual nas 16 fotos.

    Está aqui, e não só no roteiro, porque o modelo de imagem ignora o que não
    lhe é dito: sem esta linha, metade das fotos sairia com um tempo e a outra
    metade com outro, e o vídeo deixaria de parecer um único dia.
    """
    return f"WEATHER AND SEASON, the same in every photo of this story — {var.clima_en}."


def _personagens(var: Variacao) -> list[tuple[str, str]]:
    """(nome procurado na cena, bloco de descrição) de cada coadjuvante de hoje."""
    elenco = [("black", BLACK)]
    if var.convidado:
        elenco.append(
            (var.convidado.chave.lower(), var.convidado.visual)
        )
    return elenco


def _presentes(cena: dict, var: Variacao) -> list[tuple[str, str]]:
    texto = (cena.get("cena") or "").lower()
    return [(chave, bloco) for chave, bloco in _personagens(var) if chave in texto]


def _prompt(cena: dict, var: Variacao) -> str:
    partes = [ESTILO, _clima(var), GATO]
    partes += [bloco for _, bloco in _presentes(cena, var)]
    partes.append(SELFIE if cena.get("foto") == "selfie" else OUTROS)
    partes.append(f"THE PHOTO — {(cena.get('cena') or '').strip()}")
    return "\n\n".join(partes)


def _gerar(
    cfg: Config, cena: dict, var: Variacao, destino: Path, referencias: list[Path]
) -> Path:
    """Gera uma foto e salva em ``destino``. Aborta a execução se não sair.

    Não há fallback: 16 imagens é a estrutura do vídeo, e repetir uma foto para
    tapar buraco é exatamente o tipo de defeito que o espectador nota — mais
    ainda com o corte a cada 2s, em que a foto repetida volta rápido.
    """
    cliente = OpenAI(api_key=cfg.openai_api_key)
    prompt = _prompt(cena, var)

    for tentativa in range(1, TENTATIVAS + 1):
        arquivos = []
        try:
            arquivos = [open(ref, "rb") for ref in referencias]
            resposta = cliente.images.edit(
                model=cfg.imagem_model,
                image=arquivos,
                prompt=prompt,
                size=cfg.imagem_tamanho,
                quality=cfg.imagem_qualidade,
                n=1,
            )
            dados = resposta.data[0].b64_json
            if not dados:
                raise RuntimeError("resposta sem b64_json")
            destino.write_bytes(base64.b64decode(dados))
            print(f"[imagens] {destino.name} pronta ({cena.get('beat')}).")
            return destino
        except Exception as erro:  # noqa: BLE001 — tratado com retentativa
            if tentativa == TENTATIVAS:
                raise SystemExit(
                    f"Falha ao gerar {destino.name} ({cena.get('beat')}) depois de "
                    f"{TENTATIVAS} tentativas: {erro}"
                ) from erro
            espera = 5 * tentativa
            print(f"[imagens] {destino.name} falhou ({erro}); nova tentativa em {espera}s.")
            time.sleep(espera)
        finally:
            for arquivo in arquivos:
                arquivo.close()
    raise SystemExit(f"Falha inesperada ao gerar {destino.name}.")  # inalcançável


def gerar_imagens(cfg: Config, roteiro: dict, var: Variacao) -> list[Path]:
    """Gera as 16 fotos na ordem dos beats e devolve os caminhos."""
    cenas = roteiro["cenas"]
    pasta = cfg.saida / "imagens"
    pasta.mkdir(parents=True, exist_ok=True)

    if not cfg.referencia.is_file():
        raise SystemExit(
            f"Referência visual ausente em {cfg.referencia}. Ela define o gato e a "
            "estética do canal — sem ela cada vídeo sairia com um gato diferente."
        )

    caminhos: list[Path | None] = [None] * len(cenas)
    nome = lambda i: pasta / f"{i + 1:02d}_{BEATS[i][0]}.png"  # noqa: E731

    # Onda 1: para cada coadjuvante, a primeira foto em que ele aparece. Ela é
    # gerada sozinha porque vira a referência dele nas demais. Uma mesma foto
    # pode fixar dois coadjuvantes de uma vez, e é por isso que os índices são
    # coletados antes de gerar qualquer coisa.
    primeira: dict[str, int] = {}
    for chave, _ in _personagens(var):
        indice = next(
            (i for i, cena in enumerate(cenas) if chave in (cena.get("cena") or "").lower()),
            None,
        )
        if indice is not None:
            primeira[chave] = indice

    ancoras = sorted(set(primeira.values()))
    if ancoras:
        quem = ", ".join(sorted(primeira))
        print(f"[imagens] Fixando o visual de {quem} nas cenas {ancoras}...")
        with ThreadPoolExecutor(max_workers=len(ancoras)) as executor:
            futuros = {
                executor.submit(_gerar, cfg, cenas[i], var, nome(i), [cfg.referencia]): i
                for i in ancoras
            }
            for futuro, i in futuros.items():
                caminhos[i] = futuro.result()

    def referencias(i: int) -> list[Path]:
        """A estética + a foto-âncora de cada coadjuvante presente nesta cena."""
        refs = [cfg.referencia]
        for chave, _ in _presentes(cenas[i], var):
            ancora = primeira.get(chave)
            if ancora is not None and caminhos[ancora] is not None:
                refs.append(caminhos[ancora])
        return refs

    # Onda 2: o resto em paralelo. O teto subiu de 4 para 6 quando as fotos
    # passaram de 8 para 16: com 4 seriam quatro levas em vez de duas, e o cron
    # roda quatro vezes por dia com horário marcado. Seis chamadas simultâneas de
    # `high` levam ~1 min cada, o que dá ~6 requisições por minuto — bem abaixo
    # do limite da conta, que é o motivo de o teto existir.
    pendentes = [i for i in range(len(cenas)) if caminhos[i] is None]
    with ThreadPoolExecutor(max_workers=6) as executor:
        futuros = {
            executor.submit(_gerar, cfg, cenas[i], var, nome(i), referencias(i)): i
            for i in pendentes
        }
        for futuro, i in futuros.items():
            caminhos[i] = futuro.result()

    print(f"[imagens] {len(caminhos)} fotos geradas em {pasta}.")
    return [c for c in caminhos if c is not None]
