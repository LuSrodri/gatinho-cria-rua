"""Montagem do Short no ffmpeg, num único passe.

O vídeo é montado como um story do Instagram assistido de fora:

- as 16 fotos em corte seco, 2s cada (a primeira 1s), com um movimento lento de
  câmera sorteado foto a foto (foto parada lê como travada; o movimento devolve
  vida sem inventar ação que não existe);
- a barra segmentada de stories no topo, uma divisão por foto, preenchendo em
  tempo real;
- o @ do canal logo abaixo dela;
- um degradê escuro no topo, para a barra e o @ não sumirem numa foto de céu
  claro;
- as legendas de story queimadas (legendas.py);
- a trilha da ElevenLabs, costurada para dar a volta no loop.

Duas fronteiras diferentes, tratadas ao contrário uma da outra:

- a fronteira ENTRE FOTOS é para ser vista. Corte seco, sem dissolve, sem fade
  na legenda, movimento de câmera recomeçando do zero e uma divisão nova da
  barra acendendo. A cada 2s o espectador percebe que virou a página, e é isso
  que segura os 31s;
- a fronteira do VÍDEO — o fim voltando para o começo — é para não ser vista. Aí
  não há fade de saída no áudio, nem escurecimento, nem nada que anuncie o fim:
  a trilha entra em CAUDA_LOOP segundos de cruzamento que fazem o instante
  seguinte ao último quadro ser exatamente o primeiro.

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

from .config import CAUDA_LOOP, DURACOES, DUR_TOTAL, INICIOS, RAIZ, Config
from .variacao import Movimento, Variacao

# Barra de stories, em pixels para um vídeo de 1080 de largura (escalada
# proporcionalmente para outras larguras).
BARRA_MARGEM = 24
BARRA_TOPO = 26
BARRA_ALTURA = 6
BARRA_VAO = 6
# Degraus do preenchimento de cada divisão (ver _barra_stories). Dimensionado
# para o degrau durar ~0,1s, que é o limiar em que o preenchimento deixa de se
# ver pular: com a foto em 2s, são 20 degraus.
PASSOS = 20

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


def _deslocamento(mov: Movimento, lado: int, direcao: int) -> float:
    """Quantos pixels de entrada a câmera pode varrer neste eixo.

    O zoompan grampeia x e y na faixa válida sem avisar, e a faixa depende do
    zoom: no zoom mínimo do movimento sobra apenas ``lado * (1 - 1/z)/2`` para
    cada lado. Calcular a margem a partir do zoom MÍNIMO é o que impede o pan de
    bater no limite no meio do trajeto e travar — um travamento desses lê como
    vídeo com defeito, não como escolha.
    """
    if not direcao:
        return 0.0
    z_min = min(mov.z_ini, mov.z_fim)
    return lado * (1 - 1 / z_min) / 2 * mov.pan * direcao


def _cadeia_foto(indice: int, cfg: Config, frames: int, mov: Movimento) -> str:
    """Filtro que transforma uma foto 2:3 em um clipe 9:16 com movimento."""
    # O gpt-image-2 entrega 1024x1536 (2:3) e o Short é 9:16: a foto é ampliada
    # até cobrir e cortada no centro. Trabalhar o movimento no dobro da resolução
    # final e só então reduzir é o que tira o tremor do zoompan.
    largura = cfg.video_largura * 2
    altura = cfg.video_altura * 2
    fim = max(frames - 1, 1)

    # `p` vai de 0 a 1 ao longo da foto. O zoom é linear nele, e o pan vai de
    # -desloc a +desloc (daí o `2*p-1`), passando pelo centro no meio da foto.
    p = f"(on/{fim})"
    zoom = f"{mov.z_ini:.4f}+{mov.z_fim - mov.z_ini:.4f}*{p}"
    dx = _deslocamento(mov, largura, mov.dir_x)
    dy = _deslocamento(mov, altura, mov.dir_y)
    x = f"iw/2-(iw/zoom/2)+({dx:.1f})*(2*{p}-1)"
    y = f"ih/2-(ih/zoom/2)+({dy:.1f})*(2*{p}-1)"

    return (
        f"[{indice}:v]"
        f"scale={largura}:{altura}:force_original_aspect_ratio=increase,"
        f"crop={largura}:{altura},"
        f"zoompan=z='{zoom}':x='{x}':y='{y}'"
        f":d={frames}:s={cfg.video_largura}x{cfg.video_altura}:fps={cfg.fps},"
        f"setsar=1[v{indice}]"
    )


def _barra_stories(cfg: Config, total: int) -> list[str]:
    """Fundo e preenchimento da barra segmentada, uma divisão por foto.

    Com 16 divisões a barra também virou marcador de corte: cada foto acende uma
    divisão nova, então a fronteira entre duas fotos aparece no topo da tela
    mesmo quando as duas imagens têm enquadramento parecido.

    As divisões são todas do MESMO tamanho, embora a primeira foto dure metade
    das outras. É de propósito: a barra é a régua do formato, não do tempo, e uma
    divisão pela metade seria lida como defeito. O que muda na primeira é só a
    velocidade do preenchimento dela.

    O preenchimento é feito em degraus, e não com uma largura que cresce em
    função de `t`: o `drawbox` resolve `w` uma única vez, na inicialização do
    filtro, e só o `enable` é reavaliado a cada quadro. Então cada degrau é uma
    caixa de largura fixa que acende na sua fatia de tempo. Com PASSOS=20 o
    degrau tem ~3px numa divisão de ~59px, o que a 30fps não se distingue de um
    preenchimento contínuo.
    """
    escala = cfg.video_largura / 1080
    margem = BARRA_MARGEM * escala
    vao = BARRA_VAO * escala
    topo = BARRA_TOPO * escala
    altura = BARRA_ALTURA * escala
    largura_seg = (cfg.video_largura - 2 * margem - (total - 1) * vao) / total

    filtros = []
    for i in range(total):
        x = margem + i * (largura_seg + vao)
        inicio = INICIOS[i]
        passo = DURACOES[i] / PASSOS
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
            f":enable='gte(t\\,{inicio + DURACOES[i]:.3f})'"
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
    cfg: Config,
    var: Variacao,
    imagens: list[Path],
    legendas: Path,
    musica: Path | None,
    destino: Path,
) -> Path:
    """Monta o Short e devolve o caminho do arquivo final."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg não encontrado no PATH — sem ele não há vídeo.")

    total = len(imagens)
    if total != len(DURACOES):
        raise SystemExit(
            f"Chegaram {total} fotos e o formato prevê {len(DURACOES)}. A barra de "
            "stories e as legendas são calculadas a partir do formato — montar "
            "assim sairia dessincronizado."
        )
    veu = _gradiente(cfg, cfg.saida / "gradiente.png")

    comando = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for imagem in imagens:
        comando += ["-i", str(imagem.relative_to(RAIZ).as_posix())]
    comando += ["-i", str(veu.relative_to(RAIZ).as_posix())]
    # A trilha entra DUAS vezes, como duas entradas independentes do ffmpeg: uma
    # vira o corpo do vídeo, a outra vira a volta do loop. O caminho óbvio seria
    # uma entrada só com `asplit`, e é justamente o que não funciona — ver o
    # filtro de áudio adiante.
    #
    # Faixa muda em vez de nenhuma faixa: o YouTube trata vídeo sem stream de
    # áudio de forma imprevisível, e um Short mudo já é ruim o bastante sem
    # virar também um upload recusado.
    for _ in range(2):
        if musica is not None:
            comando += ["-i", str(musica.relative_to(RAIZ).as_posix())]
        else:
            comando += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]

    cadeias = [
        _cadeia_foto(i, cfg, round(DURACOES[i] * cfg.fps), var.movimentos[i])
        for i in range(total)
    ]
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

    # A trilha é costurada em anel, não aparada com fade nas pontas.
    #
    # A faixa vem com DUR_TOTAL + CAUDA_LOOP de duração. O trecho que sobra no
    # fim (a "volta") é cruzado por cima dos primeiros CAUDA_LOOP segundos do
    # corpo: durante esse cruzamento o espectador ouve o que a música TERIA
    # tocado depois do fim do vídeo desaparecendo enquanto o começo aparece. O
    # efeito é que a amostra imediatamente posterior ao último quadro é a
    # primeira, sem degrau — a música dá a volta em vez de terminar.
    #
    # É por isso que não existe mais `afade=t=out` aqui: um fade de saída é a
    # indicação mais clara que um vídeo pode dar de que está acabando, e o Short
    # reinicia sozinho. O que se quer é o contrário — que o fim não se anuncie.
    #
    # `apad` antes de tudo: se a ElevenLabs devolver uma faixa mais curta que o
    # pedido, a volta vira silêncio e o cruzamento degenera num fade de entrada
    # de CAUDA_LOOP segundos. Perde-se o anel, mas não se perde o áudio.
    #
    # A FORMA deste filtro é resultado de uma falha, e vale contar para ninguém
    # "simplificar" de volta. O caminho natural é uma entrada só, `asplit` em
    # dois ramos e um `acrossfade` juntando: escreve o anel numa linha. Isso
    # monta perfeitamente no ffmpeg 8.1.1 e FALHA no 7.1 do contêiner, com
    # "Could not open encoder before EOF" — a cadeia de áudio não entrega um
    # único quadro e o encoder AAC morre sem nunca saber o formato. O motivo é
    # que o `acrossfade` só emite depois de ler a PRIMEIRA entrada inteira, e a
    # primeira entrada (a volta) é o fim do arquivo: para chegar lá, o `asplit`
    # precisa empurrar 31s pelo outro ramo, que ninguém está consumindo. O 8.1.1
    # tolera esse acúmulo; o 7.1 desiste. Verificado nas duas versões, variante
    # por variante — só a dupla asplit+acrossfade quebra.
    #
    # Daí as duas entradas independentes e o `amix`: cada ramo lê sua própria
    # cópia do arquivo, e o amix consome os dois em paralelo, sem exigir que um
    # deles termine primeiro.
    #
    # O cruzamento em si é idêntico ao do acrossfade: `curve=tri` é ganho
    # linear, então o fade de entrada do corpo (t/d) e o de saída da volta
    # (1 - t/d) somam exatamente 1 em todo instante da sobreposição. Com
    # `normalize=0` o amix soma sem reescalar, e o resultado é o mesmo áudio —
    # com a diferença de que ele existe.
    volta_de = DUR_TOTAL
    volta_ate = DUR_TOTAL + CAUDA_LOOP
    audio = (
        f"[{total + 1}:a]apad=whole_dur={volta_ate},atrim=0:{DUR_TOTAL},"
        f"asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={CAUDA_LOOP}:curve=tri[corpo];"
        # A volta é aparada do fim, deslocada para o zero e apagada por cima do
        # começo; o `apad` final a estica com silêncio até o fim do vídeo, para
        # o amix ter os dois ramos do mesmo tamanho e não inventar transição.
        f"[{total + 2}:a]apad=whole_dur={volta_ate},atrim={volta_de}:{volta_ate},"
        f"asetpts=PTS-STARTPTS,"
        f"afade=t=out:st=0:d={CAUDA_LOOP}:curve=tri,apad=whole_dur={DUR_TOTAL}[volta];"
        f"[corpo][volta]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"aformat=sample_rates=44100:channel_layouts=stereo[aout]"
    )

    # O filtergraph vai em ARQUIVO, não na linha de comando. Ele passa de 30 mil
    # caracteres (são PASSOS degraus de barra por foto), e o Windows corta a
    # linha de comando em 32.767 — o erro que aparece lá é "o nome do arquivo ou
    # a extensão é muito grande", que não sugere nem de longe o motivo real. O
    # Linux do contêiner aguentaria, mas um pipeline que só monta vídeo no
    # servidor é um pipeline que não dá para testar.
    filtro = cfg.saida / "filtro.txt"
    filtro.write_text(
        ";".join(cadeias + [concat, veu_overlay, video, audio]), encoding="utf-8"
    )

    comando += [
        "-filter_complex_script", str(filtro.relative_to(RAIZ).as_posix()),
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
