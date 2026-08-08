"""Gatinho Cria da Rua — um Short por execução.

Um gato laranja de rua, adolescente, de um bairro arborizado da periferia de São
Paulo. Ele acorda no fim da tarde, toma um café, chama o amigo Black, passa a
noite no rolê e pega o busão para a escola quando o sol nasce. Todo dia. O vídeo
é o story que ele postou: 8 fotos tiradas por ele, 4 segundos cada, 32 segundos
no total.

    python main.py                  # gera e publica
    python main.py --sem-publicar   # gera e para (para conferir o arquivo)
    python main.py --auth-youtube   # autoriza o canal, uma vez só

Passo a passo:

1. variacao.sortear — o tempero de hoje (tempo, humor, visita, movimento). É a
   primeira coisa da execução porque todo o resto é escrito em cima dele.
2. youtube.ultimos_publicados — o que já foi ao ar, para não repetir o rolê.
3. roteiro.gerar_roteiro (gpt-5.6-luna) — os 8 beats do dia e as legendas.
4. imagens.gerar_imagens (gpt-image-2) — as 8 fotos, com o mesmo gato em todas.
   musica.gerar_musica (ElevenLabs) roda em paralelo, porque as duas esperas são
   de rede e não dependem uma da outra.
5. legendas.gerar_legendas — o .ass das caixas de story.
6. video.montar_video (ffmpeg) — corte seco, câmera lenta, barra de stories.
7. youtube.publicar — sobe o Short.
"""

import argparse
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
from pipeline.config import TOTAL_IMAGENS, carregar_config


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
    var = variacao.sortear(TOTAL_IMAGENS, inicio)

    recentes = youtube.ultimos_publicados(cfg)
    plano = roteiro.gerar_roteiro(cfg, var, recentes)

    # Imagens e trilha são as duas esperas longas da execução e não dependem uma
    # da outra: rodar em série dobraria o tempo do cron sem motivo.
    caminho_musica = cfg.saida / "trilha.mp3"
    with ThreadPoolExecutor(max_workers=2) as executor:
        futuro_musica = executor.submit(musica.gerar_musica, cfg, caminho_musica)
        fotos = imagens.gerar_imagens(cfg, plano, var)
        trilha = futuro_musica.result()

    arquivo_legendas = legendas.gerar_legendas(cfg, plano, cfg.saida / "legendas.ass")

    destino = cfg.saida / f"{_nome_arquivo(plano['titulo'])}.mp4"
    arquivo = video.montar_video(cfg, var, fotos, arquivo_legendas, trilha, destino)

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
