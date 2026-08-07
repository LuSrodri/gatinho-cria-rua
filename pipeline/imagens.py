"""As 8 fotos do story, geradas pelo gpt-image-2.

O problema difícil aqui não é fazer imagem bonita: é fazer o MESMO gato oito
vezes. Um canal de personagem morre no instante em que o espectador percebe que
o gato de cada foto é um gato diferente.

A solução é ``images.edit`` com imagem de referência (o gpt-image-2 aceita uma
lista delas e processa todas em alta fidelidade). Duas referências circulam:

- ``assets/estetica.png``, commitada no repo: define o gato laranja e a estética
  do canal. Vai em TODAS as chamadas.
- O Black, que não tem referência commitada. A primeira foto em que ele aparece
  (beat ``chamar_black``) é gerada antes das outras e vira a referência dele
  para o resto da execução.

Por isso a geração é em duas ondas: primeiro a foto que apresenta o Black,
depois todas as outras em paralelo.
"""

import base64
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from .config import BEATS, Config

TENTATIVAS = 3

# O que nunca muda de foto para foto. É o contrato visual do canal.
ESTILO = """\
STYLE — this is a photo taken on a cheap smartphone, not a professional shot.
Photorealistic. Slightly soft focus, visible sensor noise in the shadows, a bit
of motion blur if anything is moving, mild lens distortion toward the edges.
Handheld, imperfect framing. Warm colour grade, strong golden or sodium-vapour
light, deep warm shadows. The look of a real photo posted to an Instagram story
by a teenager, not a stock image.

SETTING — the outskirts of São Paulo, Brazil: unrendered red-brick houses,
concrete rooftop slabs, tangles of power lines across the sky, painted walls,
narrow alleys with steps, window grilles, plastic chairs, tiled floors. Lived-in
and ordinary, never a movie-set slum.

ABSOLUTELY NO TEXT anywhere in the image: no words, no letters, no numbers, no
signage, no logos, no watermarks, no user interface, no caption bars."""

GATO = """\
THE MAIN CAT — a young orange tabby street cat, lean, with a slightly scruffy
coat, expressive amber-green eyes and a young, cheeky face. He is a REAL cat
with normal cat anatomy: four legs, no clothes, never standing upright like a
human, never humanoid. He simply lives like a teenage boy would. Match the cat
in the reference image exactly: same fur pattern, same face, same build."""

BLACK = """\
THE BLACK CAT — his friend "Black": a short-haired solid black cat with a glossy
coat and bright yellow eyes, friendly and talkative-looking, a bit stockier than
the orange cat. Also a REAL cat with normal cat anatomy."""

SELFIE = """\
SHOT TYPE — a front-camera selfie taken by the orange cat himself. One front paw
is stretched toward the camera holding the phone, so it is large and slightly
blurred in the foreground. Low angle, tilted, close to his face, wide-angle
distortion at the edges. He is looking into the lens."""

OUTROS = """\
SHOT TYPE — a photo the orange cat took of other cats. He is NOT in the frame at
all. Candid, taken from a short distance, slightly crooked framing, as if he
raised the phone quickly to capture the moment."""


def _prompt(cena: dict, tem_black: bool) -> str:
    partes = [ESTILO, GATO]
    if tem_black:
        partes.append(BLACK)
    partes.append(SELFIE if cena.get("foto") == "selfie" else OUTROS)
    partes.append(f"THE PHOTO — {(cena.get('cena') or '').strip()}")
    return "\n\n".join(partes)


def _menciona_black(cena: dict) -> bool:
    return "black" in (cena.get("cena") or "").lower()


def _gerar(
    cfg: Config, cena: dict, destino: Path, referencias: list[Path]
) -> Path:
    """Gera uma foto e salva em ``destino``. Aborta a execução se não sair.

    Não há fallback: 8 imagens é a estrutura do vídeo, e repetir uma foto para
    tapar buraco é exatamente o tipo de defeito que o espectador nota.
    """
    cliente = OpenAI(api_key=cfg.openai_api_key)
    prompt = _prompt(cena, _menciona_black(cena))

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


def gerar_imagens(cfg: Config, roteiro: dict) -> list[Path]:
    """Gera as 8 fotos na ordem dos beats e devolve os caminhos."""
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

    # Onda 1: a foto que apresenta o Black, sozinha, porque ela vira a
    # referência dele nas demais.
    indice_black = next(
        (i for i, cena in enumerate(cenas) if _menciona_black(cena)), None
    )
    ref_black: list[Path] = []
    if indice_black is not None:
        print(f"[imagens] Fixando o visual do Black na cena {indice_black + 1}...")
        caminhos[indice_black] = _gerar(
            cfg, cenas[indice_black], nome(indice_black), [cfg.referencia]
        )
        ref_black = [caminhos[indice_black]]

    # Onda 2: o resto em paralelo. O teto de 4 é para não estourar o limite de
    # requisições por minuto da conta enquanto ainda encurta bastante a execução.
    pendentes = [i for i in range(len(cenas)) if caminhos[i] is None]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futuros = {
            executor.submit(
                _gerar,
                cfg,
                cenas[i],
                nome(i),
                [cfg.referencia] + (ref_black if _menciona_black(cenas[i]) else []),
            ): i
            for i in pendentes
        }
        for futuro, i in futuros.items():
            caminhos[i] = futuro.result()

    print(f"[imagens] {len(caminhos)} fotos geradas em {pasta}.")
    return [c for c in caminhos if c is not None]
