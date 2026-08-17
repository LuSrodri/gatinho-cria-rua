"""Gatinho Cria da Rua — um Short por execução.

Um gato laranja de rua, adolescente, de um bairro arborizado da periferia de São
Paulo. Ele acorda no fim da tarde, toma um café, chama o amigo Black, passa a
noite no rolê e pega o busão para a escola quando o sol nasce. Todo dia. O vídeo
é o story que ele postou: 8 fotos tiradas por ele, cada uma no tempo que a
história daquele dia pediu (a primeira sempre 1s, as outras de 1,3s a 3,5s) — e
o fim volta para o começo sem emenda, porque o Short reinicia sozinho e o último
beat do dia é vizinho do primeiro.

A DURAÇÃO DO VÍDEO É O QUE A HISTÓRIA SOMAR. Não há mais total fixo: um dia
corrido fecha em uns 12s e um dia que respira passa de 20s. Isso só é possível
porque o ritmo é montado ANTES de a trilha ser encomendada — quando a ElevenLabs
é chamada, o tamanho do laço já existe.

    python main.py                  # gera e publica
    python main.py --sem-publicar   # gera e para (para conferir o arquivo)
    python main.py --arco briga-1   # roda um episódio pedido em vez do dia comum
    python main.py --auth-youtube   # autoriza o canal, uma vez só

Passo a passo:

1. variacao.arco_de / variacao.sortear — o tempero de hoje (tempo, humor, visita,
   movimento) e, se houver, o episódio pedido. É a primeira coisa da execução
   porque todo o resto é escrito em cima dele.
2. youtube.ultimos_publicados — o que já foi ao ar, para não repetir o rolê.
3. roteiro.gerar_roteiro (gpt-5.6-luna) — os 8 beats do dia, as legendas e o
   ritmo de cada foto.
4. config.montar_ritmo — os ritmos viram quadros, e a soma vira a duração.
5. imagens.gerar_imagens (gpt-image-2) — as 8 fotos, com o mesmo gato em todas.
   musica.gerar_musica (ElevenLabs) roda em paralelo, porque as duas esperas são
   de rede e não dependem uma da outra.
6. legendas.gerar_legendas — o .ass das caixas de story.
7. video.montar_video (ffmpeg) — corte seco, câmera lenta, barra de stories.
8. youtube.publicar — sobe o Short.
"""

import argparse
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from pipeline import (
    imagens,
    legendas,
    musica,
    registro,
    roteiro,
    variacao,
    video,
    youtube,
)
from pipeline.config import montar_ritmo, carregar_config


def _nome_arquivo(titulo: str, limite: int = 60) -> str:
    """Slug do título para o nome do .mp4."""
    texto = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return (texto[:limite].rstrip("-") or "short")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera o Short do dia do Gatinho.")
    parser.add_argument(
        "--auth-youtube",
        action="store_true",
        help="Autoriza o canal no YouTube e salva o refresh token no .env",
    )
    parser.add_argument(
        "--sem-publicar",
        action="store_true",
        help="Gera o vídeo e para, sem subir para o YouTube",
    )
    # O arco também chega por env var porque o cron do Render não tem linha de
    # comando editável: para publicar um episódio pedido no horário, define-se
    # ARCO no serviço, deixa-se o run acontecer e tira-se a variável depois.
    parser.add_argument(
        "--arco",
        default=os.getenv("ARCO", ""),
        help=(
            "Roda um episódio pedido em vez do rolê sorteado "
            f"({', '.join(sorted(variacao.ARCOS))}). Também lido da env var ARCO."
        ),
    )
    args = parser.parse_args()

    cfg = carregar_config()

    if args.auth_youtube:
        youtube.autenticar(cfg)
        return

    inicio = datetime.now()
    print(f"=== Gatinho Cria da Rua — {inicio.strftime('%Y-%m-%d %H:%M')} ===")

    # O sorteio vem antes de tudo: o roteiro é escrito em cima dele, as imagens
    # herdam o tempo do dia e o vídeo herda o movimento de câmera. Uma semente
    # só para a execução inteira é o que mantém as três coisas coerentes.
    #
    # O arco é resolvido ANTES do sorteio, e antes de qualquer chamada de API:
    # um nome de arco errado é um erro de digitação numa env var, e o lugar de
    # descobrir isso é agora, não depois de gastar oito imagens.
    arco = variacao.arco_de(args.arco)
    var = variacao.sortear(inicio, arco)

    recentes = youtube.ultimos_publicados(cfg)
    plano = roteiro.gerar_roteiro(cfg, var, recentes)

    # O ritmo do vídeo é decidido AQUI, entre o roteiro e a montagem, porque só
    # agora existem as duas coisas de que ele precisa: a história (que diz qual
    # foto merece ficar) e a configuração (que diz quantos quadros por segundo
    # arredondar). Barra de stories, legendas e câmera passam a ler dele.
    #
    # E, desde que o total deixou de ser fixo, é este passo que decide o tamanho
    # do vídeo. Ele estar antes da trilha é o que torna isso possível: a
    # ElevenLabs é encomendada logo abaixo, e agora com um número que só existe
    # porque o roteiro já foi escrito.
    ritmo = montar_ritmo(roteiro.duracoes_pretendidas(plano), cfg.fps)
    variacao.sortear_movimentos(var, ritmo.duracoes)
    print(f"[ritmo] {ritmo.total:.2f}s em {len(ritmo)} fotos: {ritmo.resumo()}")

    # Imagens e trilha são as duas esperas longas da execução e não dependem uma
    # da outra: rodar em série dobraria o tempo do cron sem motivo.
    caminho_musica = cfg.saida / "trilha.mp3"
    with ThreadPoolExecutor(max_workers=2) as executor:
        futuro_musica = executor.submit(
            musica.gerar_musica, cfg, caminho_musica, ritmo.audio
        )
        fotos = imagens.gerar_imagens(cfg, plano, var)
        trilha = futuro_musica.result()

    arquivo_legendas = legendas.gerar_legendas(
        cfg, plano, ritmo, cfg.saida / "legendas.ass"
    )

    destino = cfg.saida / f"{_nome_arquivo(plano['titulo'])}.mp4"
    arquivo = video.montar_video(
        cfg, var, ritmo, fotos, arquivo_legendas, trilha, destino
    )

    if args.sem_publicar:
        print(f"\n[fim] Vídeo pronto em {arquivo} (não publicado, --sem-publicar).")
        return

    url = youtube.publicar(
        cfg, arquivo, plano["titulo"], plano["descricao"], plano.get("tags") or []
    )
    registro.registrar(cfg, arquivo, plano["titulo"], url)

    minutos = (datetime.now() - inicio).total_seconds() / 60
    print(f"\n[fim] {url} — execução de {minutos:.1f} min.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrompido.")
