"""As legendas de story, no formato ASS, queimadas pelo ffmpeg.

A referência visual é a caixa de texto do Instagram Stories: fundo preto
translúcido, texto branco, cantos do bloco acompanhando o comprimento de cada
linha. No ASS isso é ``BorderStyle: 3`` (caixa opaca), que desenha um retângulo
por LINHA usando a cor de contorno — que é exatamente o efeito escalonado do
Instagram quando o texto quebra em duas linhas.

Uma legenda por imagem: ela entra junto com a foto e sai junto com ela, em corte
seco. A legenda é o marcador de corte mais visível que o vídeo tem — trocar de
frase é o que o olho percebe primeiro —, então ela não desliza nem esmaece.
"""

from pathlib import Path

from PIL import ImageFont

from .config import Config, Ritmo

# Margem lateral do ASS e o respiro interno da caixa (o `Outline` do BorderStyle
# 3, que no libass vira o preenchimento entre o texto e a borda do retângulo).
# Os dois entram na conta da largura útil: a caixa desenhada é o texto MAIS dois
# respiros, e ela é que não pode encostar na margem.
MARGEM_LATERAL = 36
RESPIRO = 16

# Fração da largura do vídeo que a caixa pode ocupar. Subiu de 0,80 para 0,92, e
# essa é metade da correção de "quebras desnecessárias": a outra metade é que a
# versão anterior media só o texto e ignorava o respiro de cada lado, então
# quebrava linha antes de precisar. Agora a conta é a mesma que o libass faz.
#
# 0,92 não é um número redondo escolhido de longe: com 0,90 sobravam 940px para o
# texto, e quatro das legendas de teste mediam entre 953 e 959px — quebravam em
# duas linhas por uma dúzia de pixels. 0,92 dá 961px de texto e resolve as
# quatro. O limite superior é a margem lateral do ASS: a caixa não pode passar de
# 1080 menos as duas margens.
LARGURA_UTIL = 0.92

# Duas linhas, não três. A legenda tem de 3 a 6 palavras (roteiro.py) e a foto
# mais curta fica pouco mais de um segundo na tela: o que não se lê num relance
# não se lê. Uma terceira linha só existiria para acomodar frase comprida, e
# frase comprida é o problema, não a falta de linha.
MAX_LINHAS = 2

# Corpo da fonte em fração da largura do vídeo. 0,082 dá 89px em 1080 (era 76px).
CORPO = 0.082

# O corpo abaixo do qual não vale a pena espremer para caber em uma linha. É
# exatamente o corpo que a legenda tinha antes deste aumento (76px em 1080): a
# regra que ele define é "a legenda nunca fica MENOR do que já era, e dentro
# dessa margem uma linha ganha de duas".
#
# Essa regra é a resposta ao problema de aumentar a fonte e pedir menos quebras
# ao mesmo tempo, que são pedidos que brigam entre si: a 89px cabem umas 19
# letras por linha, e a legenda média do canal tem 20. Medido nas dezesseis
# legendas de um vídeo de teste, subir a fonte sem mais nada levava as quebras de
# 9 para 12. Com esta regra elas caem para 5, e as que sobram são as frases que
# não caberiam em uma linha em corpo nenhum.
CORPO_UMA_LINHA = 0.070

# Piso absoluto, para a frase comprida que nem em duas linhas cabe. Encolher
# além disto tornaria a legenda ilegível no tempo do corte.
CORPO_MINIMO = 62

# Altura da caixa a partir da base, em fração da altura. 0,40 põe o bloco no
# TERÇO CENTRAL da tela (a caixa de duas linhas ocupa mais ou menos de 47% a 60%
# da altura), que é onde o olho já está — ele chega na foto olhando o meio dela,
# não a barra de baixo. No terço inferior a legenda também disputava espaço com
# o título, o @ e os botões que o próprio YouTube desenha por cima do Short.
MARGEM_INFERIOR = 0.40

# &HAABBGGRR — AA=00 é opaco, AA=FF é transparente.
BRANCO = "&H00FFFFFF"
CAIXA = "&H40000000"  # preto a ~75% de opacidade

# `WrapStyle: 2` desliga a quebra automática do libass: a linha só quebra onde
# este arquivo escreveu `\\N`. É a garantia de que não sobra quebra nenhuma que
# não tenha sido decidida aqui — o libass quebrava pela conta dele, sem saber do
# corpo de fonte que `_ajustar` escolheu, e o resultado era uma palavra sozinha
# na segunda linha. Só é seguro porque a medição usa a mesma fonte, no mesmo
# corpo, e `PlayResX` é a largura real do vídeo: o que a Pillow mede aqui é o que
# o libass desenha lá.
CABECALHO = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {largura}
PlayResY: {altura}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Story,Poppins,{corpo},{branco},{branco},{caixa},{caixa},-1,0,0,0,100,100,0,0,3,{respiro},0,2,{margem_lateral},{margem_lateral},{margem_v},1

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
    """Quebra o texto no MENOR número de linhas possível, e as equilibra.

    Duas regras, nesta ordem:

    1. Não quebrar o que não precisa. Se a frase inteira cabe, ela é uma linha
       só — é assim que a legenda se lê de relance. A versão anterior enchia a
       primeira linha até o limite e empurrava o resto para baixo, o que deixava
       cabendo em uma linha frases que iam para duas por poucos pixels.
    2. Quando duas linhas são inevitáveis, escolher o ponto de quebra que deixa
       as duas linhas mais PARECIDAS. Quebra gulosa produz uma linha cheia e uma
       palavra órfã embaixo, e órfã lê como erro de montagem; duas linhas de
       tamanho parecido leem como a caixa escalonada do Instagram.

    Acima de duas linhas o equilíbrio deixa de valer a pena e a quebra volta a
    ser gulosa — nesse ponto o texto já está longo demais e quem conserta é o
    `_ajustar`, encolhendo o corpo.
    """
    palavras = texto.split()
    if not palavras:
        return [texto]
    if fonte.getlength(texto) <= largura_max:
        return [texto]

    # Duas linhas: testa cada ponto de quebra e fica com o mais equilibrado
    # entre os que cabem.
    melhor: tuple[float, list[str]] | None = None
    for corte in range(1, len(palavras)):
        a = " ".join(palavras[:corte])
        b = " ".join(palavras[corte:])
        la, lb = fonte.getlength(a), fonte.getlength(b)
        if max(la, lb) <= largura_max and (melhor is None or abs(la - lb) < melhor[0]):
            melhor = (abs(la - lb), [a, b])
    if melhor:
        return melhor[1]

    # Não coube em duas: guloso, e o `_ajustar` decide o que fazer com isso.
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
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
    """Escolhe as linhas e o corpo de fonte desta legenda.

    Três tentativas, em ordem de preferência:

    1. uma linha no corpo cheio — o melhor caso, e o que a frase curta consegue;
    2. uma linha encolhendo até CORPO_UMA_LINHA. Aqui está a decisão que importa:
       entre "89px em duas linhas" e "80px em uma", vale mais a linha única. Uma
       legenda de duas linhas obriga o olho a descer e voltar, e ele tem pouco
       mais de um segundo — enquanto nove pixels de corpo a menos ninguém
       percebe, ainda mais numa legenda que aparece sozinha e some;
    3. duas linhas equilibradas, encolhendo só se nem assim couber.
    """
    caminho = str(cfg.fontes / "Poppins-Bold.ttf")
    cheio = round(cfg.video_largura * CORPO)
    uma_linha = round(cfg.video_largura * CORPO_UMA_LINHA)

    for corpo in range(cheio, uma_linha - 1, -1):
        if ImageFont.truetype(caminho, corpo).getlength(texto) <= largura_max:
            return [texto], corpo

    corpo = cheio
    while corpo > CORPO_MINIMO:
        linhas = _quebrar(texto, ImageFont.truetype(caminho, corpo), largura_max)
        if len(linhas) <= MAX_LINHAS:
            return linhas, corpo
        corpo -= 2
    # No piso, aceita o que vier: encolher mais tornaria a legenda ilegível, e
    # três linhas curtas ainda cabem na tela.
    return _quebrar(texto, ImageFont.truetype(caminho, corpo), largura_max), corpo


def gerar_legendas(cfg: Config, roteiro: dict, ritmo: Ritmo, destino: Path) -> Path:
    """Escreve o .ass com uma legenda por foto e devolve o caminho."""
    escala = cfg.video_largura / 1080
    respiro = round(RESPIRO * escala)
    margem_lateral = round(MARGEM_LATERAL * escala)
    # O que o TEXTO pode medir: a caixa inteira menos os dois respiros que o
    # libass desenha em volta dele.
    largura_max = cfg.video_largura * LARGURA_UTIL - 2 * respiro
    corpo_base = max(CORPO_MINIMO, round(cfg.video_largura * CORPO))

    corpo = CABECALHO.format(
        largura=cfg.video_largura,
        altura=cfg.video_altura,
        corpo=corpo_base,
        branco=BRANCO,
        caixa=CAIXA,
        respiro=respiro,
        margem_lateral=margem_lateral,
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
        # Sem `\fad`. A versão anterior tinha 120ms de fade em cada ponta para a
        # legenda não aparecer de estalo — o que fazia sentido com a foto 4s na
        # tela. Com 2s, esses 240ms são 12% do tempo da legenda gastos em texto
        # meio transparente, e o pior: eles borram justamente a fronteira entre
        # uma foto e a próxima, que é o que agora precisa ser inequívoco. A
        # legenda troca junto com o corte, no mesmo quadro.
        eventos.append(
            f"Dialogue: 0,{_ts(ritmo.inicios[i])},"
            f"{_ts(ritmo.inicios[i] + ritmo.duracoes[i])},"
            f"Story,,0,0,0,,{ajuste}{conteudo}"
        )

    destino.write_text(corpo + "\n".join(eventos) + "\n", encoding="utf-8")
    quebradas = sum(1 for e in eventos if "\\N" in e)
    print(
        f"[legendas] {len(eventos)} legendas escritas em {destino.name} "
        f"({len(eventos) - quebradas} em uma linha, {quebradas} em duas)."
    )
    return destino
