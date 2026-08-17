"""A trilha do Short, composta pela API de música da ElevenLabs.

Música gerada em vez de biblioteca de faixas por um motivo prático: faixa
licenciada de terceiro é o caminho mais curto para um Content ID em cima do
canal. O que sai daqui é instrumental, original, e um pouco mais longo que o
vídeo de propósito — a sobra é o que costura o loop.

METADE DESTE ARQUIVO EXISTE PORQUE PEDIR UM LOOP NÃO PRODUZ UM LOOP.

O prompt manda, com todas as letras, não terminar: sem acorde final, sem fade,
que o último compasso entregue de volta ao primeiro. Duas coisas voltam assim
mesmo, e as duas foram medidas na faixa que o canal gerou, montando o anel de
áudio de video.py e tocando o resultado duas vezes seguidas:

- **o andamento não fecha em compasso inteiro.** O prompt pede ~75 BPM; a faixa
  veio a ~99. Não é problema em si — o problema é a consequência: a 99 BPM o
  compasso dura 2,41s, e o laço de 31 segundos dava 12,84 compassos. Não 13. Aí
  o cruzamento não salva nada, ele só MUDA DE LUGAR o estrago: enquanto a volta
  toca, a batida vem certa, porque a volta é a continuação do que estava
  tocando; quando ela se apaga e o corpo assume, a grade do corpo está fora de
  fase e a batida tropeça.

  Isso PIOROU quando o vídeo encolheu. A sobra é sempre menos de meio compasso,
  mas ela é medida contra o laço inteiro: meio compasso em 31s é 4%, e em 14s é
  9%. O conserto é o mesmo e o ajuste é maior — ver AJUSTE_MAXIMO;

  A medida que diz isso em um número: o laço tem que ter um número INTEIRO de
  pulsos, senão a primeira batida depois de recomeçar não cai onde cairia se a
  música tivesse continuado. Medido no anel, o laço dava 51,35 pulsos — um
  terço de pulso fora, o suficiente para o ouvido perceber que voltou sem saber
  dizer por quê. É a razão principal de o loop nunca ter tido loop;
- **um segundo e meio de silêncio digital no fim.** Os últimos 1,5s da faixa
  estão abaixo de -55 dBFS, e é justamente o fim da trilha que é cruzado por
  cima do começo dela. O tamanho do estrago depende de ONDE o silêncio cai
  dentro do cruzamento — no fim dele, onde a volta já está quase apagada, quase
  não se nota (0,99x da energia normal); no começo, onde a volta ainda está
  inteira, a música afunda para 0,73x e uma batida some de vez. Como a faixa era
  pedida com o tamanho exato do que se ia usar, o silêncio caía perto do começo
  do cruzamento — o pior dos dois casos.

Nenhuma das duas coisas se resolve reescrevendo o prompt: são propriedades do
áudio que voltou, e é no áudio que elas têm conserto. Então a trilha é pedida
FOLGA segundos mais longa do que precisa, e o que sobra vira margem para:

1. jogar fora o silêncio (e a introdução e a resolução) das pontas, cortando o
   trecho do MIOLO da faixa, onde ela está tocando inteira dos dois lados;
2. esticar o andamento com `atempo` o tanto que faltar para o laço dar um número
   INTEIRO de compassos. O ajuste medido na faixa real é de 1,3% — inaudível
   para quem escuta, e a diferença entre a música dar a volta e a música
   tropeçar. Com ele, o laço vai de 51,35 pulsos para 52,01: menos de um
   centésimo de pulso fora, que é a precisão da própria medida.

O laço é `Ritmo.audio`, e não a duração do vídeo: a faixa de áudio é encurtada
até fechar um bloco do AAC, e é esse tamanho que se repete quando o Short
reinicia (o porquê está em config.py). Alinhar os compassos ao vídeo deixaria a
diferença de fora da conta.

Esse número chega aqui por PARÂMETRO, e não de uma constante importada, porque o
vídeo deixou de ter duração fixa: o tamanho do laço só existe depois que o
roteiro do dia decide os cortes. Quando `gerar_musica` é chamada, ele já está
decidido — o ritmo é montado antes da trilha ser encomendada (ver main.py).

O compasso é medido por autocorrelação do envelope de ataque (ver `_compasso`),
com a stdlib e nada mais. Note que errar o compasso por uma oitava (achar meio
compasso, ou dois) quase não muda o resultado: qualquer que seja a unidade
encontrada, o que se pede a ela é caber um número inteiro de vezes no laço, e um
múltiplo do compasso cabe inteiro exatamente quando o compasso cabe.
"""

import subprocess
from array import array
from pathlib import Path

import requests

from .config import CAUDA_LOOP, TAXA_AUDIO, Config

API_MUSICA = "https://api.elevenlabs.io/v1/music"

# Quanto se pede além do que o vídeo usa. É a matéria-prima do recorte: dá para
# jogar fora as pontas mortas e ainda escolher onde o trecho começa. 8s são
# generosos de propósito — a chamada custa o mesmo e sobrar é barato.
FOLGA = 8.0

# Análise do áudio. 22.050 Hz mono é de sobra para achar batida (o que interessa
# está muito abaixo de 11 kHz) e deixa a autocorrelação em pura stdlib rodar em
# fração de segundo.
TAXA = 22050
SALTO = 256  # amostras por quadro do envelope (~12ms)

# Abaixo desta fração do pico, o áudio é considerado silêncio de ponta. -34 dB
# relativos: na faixa medida, o silêncio do fim estava 45 dB abaixo do pico e o
# ponto mais quieto DA MÚSICA estava 27 dB abaixo. Cabe folga dos dois lados.
LIMIAR_SILENCIO = 0.02

# Onde procurar a batida, em segundos por pulso: de 50 a 170 BPM. E o compasso
# resultante, dobrado ou dividido até cair nesta faixa — é a duração de um
# compasso 4/4 entre 60 e 120 BPM.
FAIXA_PULSO = (0.35, 1.2)
FAIXA_COMPASSO = (2.0, 4.0)

# Abaixo desta correlação, a medição não convence e a trilha vai sem esticar:
# esticar por um compasso errado é pior do que não esticar.
CONFIANCA_MINIMA = 0.15

# Teto do ajuste de andamento. Ele SUBIU de 0,08 para 0,20 quando o vídeo deixou
# de ter 31s fixos, e o motivo é aritmética, não gosto.
#
# O que se pede ao `atempo` é sempre a mesma coisa: fechar a fração de compasso
# que sobra no laço, que por construção é menos de meio compasso. Só que o ajuste
# é essa sobra DIVIDIDA PELO LAÇO, e o laço encolheu. Com 31s e um compasso de
# 2,4s, meio compasso era 3,9%; com um vídeo de 11s (o dia mais corrido possível)
# e um compasso de 4s (o topo de FAIXA_COMPASSO), meio compasso é 18%.
#
# Manter 0,08 não pouparia nada: a trilha simplesmente iria sem esticar, e o laço
# tropeçaria toda volta — que é o defeito que este arquivo inteiro existe para
# consertar. E 18% de andamento numa faixa que ninguém nunca ouviu não é audível
# como "rápido": não existe original com que comparar, o `atempo` não mexe na
# afinação, e o que sai é uma faixa lo-fi num BPM levemente diferente do que a
# ElevenLabs sorteou.
#
# O teto não some porque ele nunca foi sobre fidelidade: ele é a rede contra
# MEDIÇÃO ERRADA. Um pedido de ajuste acima disto não é uma sobra de compasso, é
# um compasso que foi medido errado — e esticar por um compasso errado é pior do
# que não esticar.
AJUSTE_MAXIMO = 0.20

# Quanto o recorte pode entrar na faixa, no máximo, procurando o miolo dela.
DESLOCAMENTO_MAXIMO = 4.0

# O prompt é fixo: a identidade sonora do canal não deve mudar a cada execução,
# do mesmo jeito que a estética visual não muda. O que varia é só a semente
# implícita da geração.
PROMPT = """\
Instrumental lo-fi hip hop for a short film about a teenage street cat wandering
a leafy neighbourhood on the outskirts of São Paulo at golden hour and through
the night.

Dusty boom-bap drums, soft and unhurried, around 90 BPM, steady 4/4 throughout.
A warm, slightly detuned electric piano playing a simple tender loop in a major
key. A round, gentle bass line. A soft nylon-string guitar figure somewhere
underneath. Vinyl crackle, distant traffic, the hum of a warm evening.

The feeling is intimate, warm and quietly hopeful — nostalgic but content, calm
but awake. Nothing dramatic, no build, no drop. It should feel like a loop you
could stare out of a bus window to on a good morning.

IT IS A LOOP, NOT A PIECE. Stay in the same key, the same tempo and the same
groove from the first bar to the last. Do not build toward anything, do not
resolve, and above all do not end: no final chord, no ritardando, no cymbal
swell, no fade-out. The last bars must sound like they are handing straight back
to the first ones, so that playing the track twice in a row has no seam.

The full band is already playing at the very first sample and is still playing at
the very last one. No intro, no count-in, no silence or near-silence at either
end.

No vocals, no lyrics, no voices."""


def _envelope(caminho: Path) -> tuple[list[float], float]:
    """Decodifica a faixa e devolve o envelope de energia e o pico dele.

    Um valor por SALTO amostras, cada um a média do valor absoluto do bloco. É
    a representação mais barata que serve para as duas perguntas deste arquivo
    — onde a música começa e para de tocar, e de quanto em quanto tempo ela
    bate.
    """
    bruto = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(caminho),
         "-ac", "1", "-ar", str(TAXA), "-f", "s16le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    amostras = array("h")
    amostras.frombytes(bruto[: len(bruto) - len(bruto) % amostras.itemsize])

    env = [
        sum(abs(v) for v in amostras[i : i + SALTO]) / SALTO
        for i in range(0, len(amostras) - SALTO, SALTO)
    ]
    return env, max(env, default=0.0)


def _bordas(env: list[float], pico: float) -> tuple[float, float]:
    """Primeiro e último instante em que a faixa está de fato tocando."""
    limiar = pico * LIMIAR_SILENCIO
    tocando = [i for i, v in enumerate(env) if v > limiar]
    if not tocando:
        return 0.0, len(env) * SALTO / TAXA
    return tocando[0] * SALTO / TAXA, (tocando[-1] + 1) * SALTO / TAXA


def _correlacao(ataque: list[float], atraso: int) -> float:
    """Autocorrelação do ataque em um atraso, normalizada pelo trecho que sobra.

    A normalização pelo número de termos importa: sem ela, atrasos grandes
    somam menos produtos e parecem sempre piores que atrasos pequenos, o que
    atrapalha justamente o refinamento em múltiplos altos.
    """
    sobra = len(ataque) - atraso
    if sobra <= 0:
        return 0.0
    return sum(ataque[i] * ataque[i + atraso] for i in range(sobra)) / sobra


def _cume(ataque: list[float], centro: int, raio: float) -> float:
    """Atraso do pico da autocorrelação perto de ``centro``, com casas decimais.

    O atraso é medido em quadros do envelope, que são discretos — e a precisão
    de um quadro inteiro não basta aqui: a 12ms por quadro, um pulso de 0,6s tem
    2% de erro, que é MAIOR que o ajuste de andamento que este arquivo aplica.
    Corrigir um erro de 1,3% com uma medida de ±2% é ruído.

    A saída são três amostras em volta do pico ajustadas por uma parábola (o
    truque clássico de interpolação de pico): o vértice dela cai entre os
    quadros, e é ele que se devolve.
    """
    melhor = max(
        range(max(centro - round(raio), 1), centro + round(raio) + 1),
        key=lambda a: _correlacao(ataque, a),
        default=centro,
    )
    a, b, c = (_correlacao(ataque, melhor + d) for d in (-1, 0, 1))
    curvatura = a - 2 * b + c
    if curvatura >= 0:  # não é um pico; fica o quadro inteiro mesmo
        return float(melhor)
    return melhor + 0.5 * (a - c) / curvatura


def _compasso(env: list[float]) -> tuple[float, float]:
    """Mede a duração de um compasso, por autocorrelação do ataque.

    O envelope de energia sozinho não serve: ele é dominado pelo nível médio da
    música, e o que marca o tempo é a SUBIDA de energia (a batida entrando), não
    a energia em si. Daí a derivada retificada — só o que cresceu, e o quanto
    cresceu. A autocorrelação disso tem um pico em cada múltiplo do pulso.

    A medida é feita em dois passos, e o segundo é o que a torna utilizável. O
    primeiro varre a faixa de pulsos plausíveis e acha o pulso, com a precisão
    grosseira de um quadro de envelope. O segundo vai procurar o pico em
    MÚLTIPLOS cada vez mais altos do pulso e divide o atraso encontrado pelo
    número de batidas: o mesmo erro de medida, dividido pelo múltiplo. É a
    diferença entre saber o andamento a 2% e sabê-lo a 0,1%, e é 2% que estraga a
    conta do loop, porque a correção que se vai aplicar é de 1,3%.

    O refinamento vai DOBRANDO o múltiplo, e não pula direto para o mais alto que
    couber. Pular direto é o que estava aqui antes, e tem um jeito silencioso de
    dar errado: a autocorrelação tem um pico em CADA múltiplo do pulso, e o erro
    do palpite grosseiro, multiplicado por dezesseis, desloca o centro da busca
    quase um pulso inteiro — aí a janela encontra o pico VIZINHO e devolve um
    andamento errado por 1/múltiplo, uns 3%, com toda a cara de estar certo.
    Dobrando, cada rodada refina o palpite antes de a próxima precisar dele, e o
    centro nunca sai de um quarto de pulso do lugar.

    Devolve (duração do compasso em segundos, confiança de 0 a 1).
    """
    taxa = TAXA / SALTO
    ataque = [max(env[i + 1] - env[i], 0.0) for i in range(len(env) - 1)]
    if len(ataque) < 4:
        return 0.0, 0.0
    media = sum(ataque) / len(ataque)
    ataque = [v - media for v in ataque]

    energia = _correlacao(ataque, 0)
    if energia <= 0:
        return 0.0, 0.0

    inicio = max(round(FAIXA_PULSO[0] * taxa), 1)
    fim = min(round(FAIXA_PULSO[1] * taxa), len(ataque) // 3)
    if fim <= inicio:
        return 0.0, 0.0
    grosso = max(range(inicio, fim + 1), key=lambda a: _correlacao(ataque, a))
    confianca = _correlacao(ataque, grosso) / energia

    # Refina dobrando o múltiplo enquanto sobrarem dois terços da faixa se
    # sobrepondo — abaixo disso a correlação vira ruído de poucas amostras.
    limite = len(ataque) * 2 / 3
    pulso, multiplo = float(grosso), 1
    while 2 * multiplo * pulso <= limite:
        multiplo *= 2
        pulso = _cume(ataque, round(multiplo * pulso), pulso / 4) / multiplo
    pulso /= taxa

    # Do pulso encontrado para uma unidade do tamanho de um compasso. Dobrar ou
    # dividir é seguro porque o que se vai exigir dela — caber um número inteiro
    # de vezes no laço — vale igual para o compasso e para seus múltiplos.
    compasso = pulso
    while 0 < compasso < FAIXA_COMPASSO[0]:
        compasso *= 2
    while compasso > FAIXA_COMPASSO[1]:
        compasso /= 2
    return compasso, confianca


def _ajuste_de_andamento(compasso: float, confianca: float, dur_audio: float) -> float:
    """Fator de `atempo` que faz o laço dar um número inteiro de compassos."""
    if not compasso or confianca < CONFIANCA_MINIMA:
        print(
            f"[musica] Compasso não identificado com segurança (confiança "
            f"{confianca:.2f}); a trilha vai no andamento original."
        )
        return 1.0
    compassos = max(round(dur_audio / compasso), 1)
    fator = compassos * compasso / dur_audio
    if abs(fator - 1) > AJUSTE_MAXIMO:
        print(f"[musica] Ajuste de andamento de {fator:.3f}x é grande demais; ignorado.")
        return 1.0
    print(
        f"[musica] Compasso de {compasso:.3f}s ({240 / compasso:.0f} BPM em 4/4, "
        f"confiança {confianca:.2f}): {compassos} compassos em {dur_audio:.3f}s "
        f"com andamento {fator:.4f}x."
    )
    return fator


def _costurar(bruta: Path, destino: Path, dur_audio: float) -> Path:
    """Recorta o miolo da faixa e ajusta o andamento; devolve o destino.

    O que sai daqui tem exatamente ``dur_audio + CAUDA_LOOP`` segundos, sem
    silêncio nas pontas e com os ``dur_audio`` iniciais valendo um número inteiro
    de compassos — que é a forma que o anel de áudio de video.py precisa receber
    para o fim voltar ao começo sem tropeço.
    """
    precisa = dur_audio + CAUDA_LOOP
    env, pico = _envelope(bruta)
    inicio, fim = _bordas(env, pico)
    disponivel = fim - inicio
    print(
        f"[musica] Faixa de {len(env) * SALTO / TAXA:.1f}s, tocando de "
        f"{inicio:.2f}s a {fim:.2f}s."
    )
    if disponivel <= 1.0:
        raise ValueError(f"a faixa só tem {disponivel:.2f}s de som")

    fator = _ajuste_de_andamento(*_compasso(env), dur_audio)
    largura = precisa * fator

    # Onde começar dentro da faixa. O meio do que sobra, com teto: o começo de
    # uma faixa gerada costuma ser o instrumento entrando sozinho e o fim
    # costuma ser a resolução — os dois lugares onde o cruzamento do loop
    # encontraria uma música diferente da que estava tocando.
    desloc = inicio + min(max((disponivel - largura) / 2, 0.0), DESLOCAMENTO_MAXIMO)

    # Se a ElevenLabs devolver menos do que foi pedido, o trecho útil repete até
    # dar a largura. Repetir tem sua própria emenda, e ela se ouve — e, quando
    # falta pouco, ela cai perto do fim, que é justamente onde não se queria. Mas
    # a alternativa era o `apad` completando com silêncio, e aí não é uma emenda
    # no meio da música: é a música sumindo na volta do loop, que é o defeito que
    # este arquivo inteiro existe para consertar. É modo degradado dos dois
    # jeitos; este avisa e soa melhor.
    repetir = disponivel < largura
    filtros = [
        # A taxa é fixada antes do `aloop` porque o tamanho do laço é dado em
        # AMOSTRAS, e sem fixar não há como saber quantas são um segundo.
        f"aformat=sample_rates={TAXA_AUDIO}",
        f"atrim=start={desloc:.6f}:end={fim:.6f}",
        "asetpts=N/SR/TB",
    ]
    if repetir:
        print(
            f"[aviso] A faixa tem {disponivel:.1f}s de som para {largura:.1f}s de "
            "trilha; o trecho vai repetir para completar."
        )
        filtros.append(f"aloop=loop=-1:size={round((fim - desloc) * TAXA_AUDIO)}")
    filtros += [
        f"atrim=duration={largura:.6f}",
        "asetpts=N/SR/TB",
        f"atempo={fator:.6f}",
        f"atrim=duration={precisa:.6f}",
        "asetpts=N/SR/TB",
        f"apad=whole_dur={precisa:.6f}",
    ]
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(bruta),
         "-af", ",".join(filtros), "-c:a", "libmp3lame", "-b:a", "192k", str(destino)],
        check=True,
    )
    print(
        f"[musica] Trecho de {desloc:.2f}s a {min(desloc + largura, fim):.2f}s virou "
        f"{precisa:.0f}s de trilha em {destino.name}."
    )
    return destino


def gerar_musica(cfg: Config, destino: Path, dur_audio: float) -> Path | None:
    """Compõe a trilha do tamanho do laço e devolve o caminho; None se falhar.

    ``dur_audio`` é ``Ritmo.audio``: a duração do laço de áudio do vídeo de hoje.
    Ela vem de fora porque o vídeo não tem mais duração fixa — quem chama já sabe
    quanto o dia somou, e é esse número que a trilha precisa cobrir.

    Falha aqui NÃO derruba a execução: um Short mudo ainda é um Short no ar, e
    perder o vídeo inteiro por causa da trilha seria trocar um problema pequeno
    por um grande. O ffmpeg cobre o buraco com uma faixa silenciosa (video.py).
    """
    print("[musica] Compondo a trilha do vídeo...")
    bruta = destino.with_name(f"{destino.stem}-bruta{destino.suffix}")
    try:
        resposta = requests.post(
            API_MUSICA,
            params={"output_format": "mp3_44100_128"},
            headers={
                "xi-api-key": cfg.elevenlabs_api_key,
                "Content-Type": "application/json",
            },
            json={
                # A sobra não é margem de segurança: é matéria-prima. CAUDA_LOOP
                # segundos são cruzados por cima do começo da faixa para a trilha
                # dar a volta no loop (ver video.py), e FOLGA segundos são o que
                # `_costurar` gasta jogando fora as pontas mortas e escolhendo de
                # onde recortar.
                "prompt": PROMPT,
                "music_length_ms": int((dur_audio + CAUDA_LOOP + FOLGA) * 1000),
                "model_id": cfg.musica_model,
                "force_instrumental": True,
            },
            timeout=300,
        )
        if resposta.status_code != 200:
            # A ElevenLabs devolve 401 tanto para chave errada quanto para chave
            # CERTA sem escopo — e chaves de lá são restringíveis por endpoint.
            # Repetir a mensagem da API em vez de adivinhar é o que separa
            # "gere outra chave" de "marque music_generation nesta chave".
            print(
                f"[aviso] ElevenLabs recusou a trilha ({resposta.status_code}): "
                f"{resposta.text[:300]}. Vídeo sairá mudo."
            )
            return None
        bruta.write_bytes(resposta.content)
    except requests.RequestException as erro:
        print(f"[aviso] Falha ao compor a trilha ({erro}); vídeo sairá mudo.")
        return None

    try:
        return _costurar(bruta, destino, dur_audio)
    except (subprocess.CalledProcessError, OSError, ValueError) as erro:
        # A costura é uma melhora, não um requisito: se a análise falhar, a faixa
        # crua ainda toca. O loop fica pior, o vídeo sai.
        print(f"[aviso] Falha ao costurar a trilha ({erro}); vai a faixa crua.")
        destino.write_bytes(bruta.read_bytes())
        return destino
