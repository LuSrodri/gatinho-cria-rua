"""As legendas de story, no formato ASS, queimadas pelo ffmpeg.

A referência visual é a caixa de texto do Instagram Stories: fundo preto
translúcido, texto branco, cantos do bloco acompanhando o comprimento de cada
linha. No ASS isso é ``BorderStyle: 3`` (caixa opaca), que desenha um retângulo
por LINHA usando a cor de contorno — que é exatamente o efeito escalonado do
Instagram quando o texto quebra em duas linhas.

Uma legenda por imagem: ela entra junto com a foto e sai junto com ela.
"""

from pathlib import Path

from PIL import ImageFont

from .config import DUR_IMAGEM, Config

# Fração da largura do vídeo que o texto pode ocupar. O Instagram deixa a caixa
# respirar; texto colado na borda entrega que é legenda queimada, não story.
LARGURA_UTIL = 0.76
MAX_LINHAS = 2

# Corpo da fonte em fração da largura do vídeo, e o piso ao encolher. Story é
# lido de relance: abaixo de ~40px em 1080 a legenda deixa de competir com a
# foto e vira ruído.
CORPO = 0.050
CORPO_MINIMO = 40

# Altura da caixa a partir da base, em fração da altura. Fica no terço inferior,
# livre da barra de stories no topo e do rodapé da interface do Shorts.
MARGEM_INFERIOR = 0.20

# &HAABBGGRR — AA=00 é opaco, AA=FF é transparente.
BRANCO = "&H00FFFFFF"
CAIXA = "&H40000000"  # preto a ~75% de opacidade

CABECALHO = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {largura}
PlayResY: {altura}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Story,Poppins,{corpo},{branco},{branco},{caixa},{caixa},-1,0,0,0,100,100,0,0,3,18,0,2,60,60,{margem_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(segundos: float) -> str:
    segundos = max(0.0, segundos)
    return (
        f"{int(segundos // 3600)}:"
        f"{int(segundos % 3600 // 60):02d}:"
        f"{segundos % 60:05.2f}"
    )


def _quebrar(texto: str, fonte: ImageFont.FreeTypeFont, largura_max: float) -> list[str]:
    """Quebra o texto em linhas medindo a fonte de verdade."""
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if atual and fonte.getlength(tentativa) > largura_max:
            linhas.append(atual)
            atual = palavra
        else:
            atual = tentativa
    if atual:
        linhas.append(atual)
    return linhas or [texto]


def _ajustar(texto: str, cfg: Config, largura_max: float) -> tuple[list[str], int]:
    """Acha o maior corpo de fonte em que o texto cabe em até MAX_LINHAS."""
    caminho = str(cfg.fontes / "Poppins-Bold.ttf")
    corpo = max(CORPO_MINIMO, round(cfg.video_largura * CORPO))
    while corpo > CORPO_MINIMO:
        linhas = _quebrar(texto, ImageFont.truetype(caminho, corpo), largura_max)
        if len(linhas) <= MAX_LINHAS:
            return linhas, corpo
        corpo -= 2
    # No piso, aceita o que vier: encolher mais tornaria a legenda ilegível, e
    # três linhas curtas ainda cabem na tela.
    return _quebrar(texto, ImageFont.truetype(caminho, corpo), largura_max), corpo


def gerar_legendas(cfg: Config, roteiro: dict, destino: Path) -> Path:
    """Escreve o .ass com uma legenda por foto e devolve o caminho."""
    largura_max = cfg.video_largura * LARGURA_UTIL
    corpo_base = max(CORPO_MINIMO, round(cfg.video_largura * CORPO))

    corpo = CABECALHO.format(
        largura=cfg.video_largura,
        altura=cfg.video_altura,
        corpo=corpo_base,
        branco=BRANCO,
        caixa=CAIXA,
        margem_v=round(cfg.video_altura * MARGEM_INFERIOR),
    )

    eventos = []
    for i, cena in enumerate(roteiro["cenas"]):
        texto = (cena.get("legenda") or "").strip()
        if not texto:
            continue
        linhas, tam = _ajustar(texto, cfg, largura_max)
        # Chaves são sintaxe de override no ASS; um "{" solto na legenda
        # engoliria o resto da linha.
        conteudo = "\\N".join(linhas).replace("{", "(").replace("}", ")")
        ajuste = f"{{\\fs{tam}}}" if tam != corpo_base else ""
        # Fade curto nas pontas: o corte entre fotos é seco (é story), mas a
        # legenda aparecendo de estalo junto com o corte pesa a leitura.
        eventos.append(
            f"Dialogue: 0,{_ts(i * DUR_IMAGEM)},{_ts((i + 1) * DUR_IMAGEM)},"
            f"Story,,0,0,0,,{ajuste}{{\\fad(120,120)}}{conteudo}"
        )

    destino.write_text(corpo + "\n".join(eventos) + "\n", encoding="utf-8")
    print(f"[legendas] {len(eventos)} legendas escritas em {destino.name}.")
    return destino
