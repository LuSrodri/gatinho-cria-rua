"""Montagem do Short no ffmpeg, num único passe.

O vídeo é montado como um story do Instagram assistido de fora:

- as 8 fotos em corte seco, 2,5s cada, com um zoom lento (foto parada por 2,5s
  lê como travada; o zoom devolve vida sem inventar movimento que não existe);
- a barra segmentada de stories no topo, uma divisão por foto, preenchendo em
  tempo real;
- o @ do canal logo abaixo dela;
- um degradê escuro no topo, para a barra e o @ não sumirem numa foto de céu
  claro;
- as legendas de story queimadas (legendas.py);
- a trilha da ElevenLabs, com fade nas pontas.

Tudo em um `filter_complex` só: dois passes de codificação custariam qualidade
sem ganhar nada, já que a fonte são PNGs.

Os caminhos entram no filtro como RELATIVOS, com o ffmpeg rodando a partir da
raiz do projeto. Caminho absoluto do Windows tem `C:` no meio, e dois-pontos é
separador de argumento no filtergraph do ffmpeg — o que quebraria o teste local
sem dar nenhum sinal claro do motivo.
"""

import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .config import DUR_IMAGEM, DUR_TOTAL, RAIZ, Config

# Barra de stories, em pixels para um vídeo de 1080 de largura (escalada
# proporcionalmente para outras larguras).
BARRA_MARGEM = 24
BARRA_TOPO = 26
BARRA_ALTURA = 6
BARRA_VAO = 6
# Degraus do preenchimento de cada divisão (ver _barra_stories).
PASSOS = 25

# Véu escuro do topo, para a barra e o @ não sumirem numa foto de céu claro.
DEGRADE_ALTURA = 0.115  # fração da altura do vídeo
DEGRADE_OPACIDADE = 0.45  # alfa no topo, caindo a zero na base do degradê


def _gradiente(cfg: Config, destino: Path) -> Path:
    """Gera o PNG do véu do topo (preto opaco em cima, transparente embaixo).

    Empilhar retângulos de alfa decrescente no ffmpeg seria mais simples, mas os
    degraus aparecem: num céu liso, cada salto de alfa vira uma listra. Um PNG
    com rampa de 1px por linha não tem esse problema.
    """
    altura = round(cfg.video_altura * DEGRADE_ALTURA)
    # A rampa é montada numa coluna de 1px e esticada na horizontal: o degradê
    # é vertical, então as 1080 colunas são todas iguais.
    coluna = Image.new("RGBA", (1, altura))
    for y in range(altura):
        # Queda quadrática: segura a opacidade onde estão a barra e o @, e
        # dissolve rápido depois, para o véu não pesar sobre a foto.
        alfa = round(255 * DEGRADE_OPACIDADE * (1 - y / altura) ** 2)
        coluna.putpixel((0, y), (0, 0, 0, alfa))
    coluna.resize((cfg.video_largura, altura), Image.NEAREST).save(destino)
    return destino


def _zoom(indice: int, frames: int) -> str:
    """Expressão de zoom da foto: ímpares fecham, pares abrem.

    Alternar a direção evita a sensação de esteira que dá quando oito fotos
    seguidas fazem exatamente o mesmo movimento.
    """
    fim = max(frames - 1, 1)
    if indice % 2 == 0:
        return f"1.0+0.10*on/{fim}"
    return f"1.10-0.10*on/{fim}"


def _cadeia_foto(indice: int, cfg: Config, frames: int) -> str:
    """Filtro que transforma uma foto 2:3 em um clipe 9:16 com zoom."""
    # O gpt-image-2 entrega 1024x1536 (2:3) e o Short é 9:16: a foto é ampliada
    # até cobrir e cortada no centro. Trabalhar o zoom no dobro da resolução
    # final e só então reduzir é o que tira o tremor do zoompan.
    largura = cfg.video_largura * 2
    altura = cfg.video_altura * 2
    return (
        f"[{indice}:v]"
        f"scale={largura}:{altura}:force_original_aspect_ratio=increase,"
        f"crop={largura}:{altura},"
        f"zoompan=z='{_zoom(indice, frames)}'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={cfg.video_largura}x{cfg.video_altura}:fps={cfg.fps},"
        f"setsar=1[v{indice}]"
    )


def _barra_stories(cfg: Config, total: int) -> list[str]:
    """Fundo e preenchimento da barra segmentada, uma divisão por foto.

    O preenchimento é feito em degraus, e não com uma largura que cresce em
    função de `t`: o `drawbox` resolve `w` uma única vez, na inicialização do
    filtro, e só o `enable` é reavaliado a cada quadro. Então cada degrau é uma
    caixa de largura fixa que acende na sua fatia de tempo. Com PASSOS=25 o
    degrau tem ~5px numa divisão de ~124px, o que a 30fps não se distingue de um
    preenchimento contínuo.
    """
    escala = cfg.video_largura / 1080
    margem = BARRA_MARGEM * escala
    vao = BARRA_VAO * escala
    topo = BARRA_TOPO * escala
    altura = BARRA_ALTURA * escala
    largura_seg = (cfg.video_largura - 2 * margem - (total - 1) * vao) / total
    passo = DUR_IMAGEM / PASSOS

    filtros = []
    for i in range(total):
        x = margem + i * (largura_seg + vao)
        inicio = i * DUR_IMAGEM
        base = f"drawbox=x={x:.2f}:y={topo:.2f}:h={altura:.2f}"

        # Trilho apagado da divisão, sempre visível.
        filtros.append(f"{base}:w={largura_seg:.2f}:color=white@0.35:t=fill")

        # Os degraus do preenchimento, um aceso por vez.
        for k in range(PASSOS):
            largura = largura_seg * (k + 1) / PASSOS
            de = inicio + k * passo
            ate = de + passo
            filtros.append(
                f"{base}:w={largura:.2f}:color=white@0.95:t=fill"
                f":enable='between(t\\,{de:.3f}\\,{ate:.3f})'"
            )

        # Depois que a foto passa, a divisão fica cheia até o fim do vídeo —
        # como as stories já vistas no Instagram.
        filtros.append(
            f"{base}:w={largura_seg:.2f}:color=white@0.95:t=fill"
            f":enable='gte(t\\,{inicio + DUR_IMAGEM:.3f})'"
        )
    return filtros


def _handle(cfg: Config) -> str:
    """O @ do canal, logo abaixo da barra de stories."""
    escala = cfg.video_largura / 1080
    # `\:` porque dois-pontos separa opções dentro do drawtext.
    texto = f"{cfg.handle} · agora".replace(":", "\\:")
    return (
        f"drawtext=fontfile=fonts/Poppins-SemiBold.ttf:text='{texto}'"
        f":fontcolor=white@0.92:fontsize={round(30 * escala)}"
        f":x={round(26 * escala)}:y={round(52 * escala)}"
        f":shadowcolor=black@0.45:shadowx=0:shadowy={max(1, round(2 * escala))}"
    )


def montar_video(
    cfg: Config, imagens: list[Path], legendas: Path, musica: Path | None, destino: Path
) -> Path:
    """Monta o Short e devolve o caminho do arquivo final."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg não encontrado no PATH — sem ele não há vídeo.")

    frames = round(DUR_IMAGEM * cfg.fps)
    total = len(imagens)
    veu = _gradiente(cfg, cfg.saida / "gradiente.png")

    comando = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for imagem in imagens:
        comando += ["-i", str(imagem.relative_to(RAIZ).as_posix())]
    comando += ["-i", str(veu.relative_to(RAIZ).as_posix())]
    if musica is not None:
        comando += ["-i", str(musica.relative_to(RAIZ).as_posix())]
    else:
        # Faixa muda em vez de nenhuma faixa: o YouTube trata vídeo sem stream
        # de áudio de forma imprevisível, e um Short mudo já é ruim o bastante
        # sem virar também um upload recusado.
        comando += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]

    cadeias = [_cadeia_foto(i, cfg, frames) for i in range(total)]
    concat = "".join(f"[v{i}]" for i in range(total)) + f"concat=n={total}:v=1:a=0[seq]"

    # A ORDEM importa: o véu vai primeiro, e barra e @ vêm por cima dele. Ao
    # contrário, o véu escureceria justamente os dois elementos que ele existe
    # para tornar legíveis.
    veu_overlay = f"[seq][{total}:v]overlay=0:0[comveu]"
    sobreposicoes = _barra_stories(cfg, total) + [_handle(cfg)]
    # `fontsdir` aponta para as fontes do repo: sem isso o libass cairia na
    # fonte padrão do sistema, que no contêiner não é a Poppins.
    sobreposicoes.append(
        f"subtitles={legendas.relative_to(RAIZ).as_posix()}:fontsdir=fonts"
    )
    video = "[comveu]" + ",".join(sobreposicoes) + "[vout]"

    saida_audio = 1.5
    # `apad` antes do corte: se a ElevenLabs devolver uma faixa mais curta que o
    # pedido, o vídeo terminaria sem áudio nos últimos segundos em vez de com o
    # fade — silêncio no fim lê como bug de codificação.
    audio = (
        f"[{total + 1}:a]apad,atrim=0:{DUR_TOTAL},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d=0.6,"
        f"afade=t=out:st={DUR_TOTAL - saida_audio}:d={saida_audio},"
        f"aformat=sample_rates=44100:channel_layouts=stereo[aout]"
    )

    comando += [
        "-filter_complex", ";".join(cadeias + [concat, veu_overlay, video, audio]),
        "-map", "[vout]",
        "-map", "[aout]",
        "-t", str(DUR_TOTAL),
        "-r", str(cfg.fps),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(destino.relative_to(RAIZ).as_posix()),
    ]

    print(f"[video] Montando {destino.name} ({DUR_TOTAL:.0f}s, {total} fotos)...")
    resultado = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise SystemExit(
            "ffmpeg falhou na montagem do vídeo:\n"
            f"{resultado.stderr[-2000:]}"
        )
    if not destino.is_file() or destino.stat().st_size == 0:
        raise SystemExit(f"ffmpeg terminou sem erro mas {destino} está vazio.")

    print(f"[video] Pronto: {destino} ({destino.stat().st_size / 1e6:.1f} MB)")
    return destino
