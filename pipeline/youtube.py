"""Publicação no YouTube via Data API v3, só com ``requests``.

O fluxo é o mesmo do automacao-video: uma vez, ``autenticar()`` roda o
consentimento OAuth no navegador e guarda um refresh token de longa duração no
.env; a cada execução, ``publicar()`` troca esse token por um access token curto
e sobe o vídeo num upload resumível.

A porta do redirect é FIXA (``PORTA_AUTH``), diferente do automacao-video, que
sorteia uma. O motivo é prático: com porta fixa dá para montar a URL de
autorização fora do programa e mandar pronta para quem vai autorizar.
"""

import http.server
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests

from .config import Config, atualizar_env

# Só o que este canal usa: subir vídeo e ler os últimos publicados. O
# automacao-video pede a lista inteira de escopos porque também mexe em
# playlists, comentários e Analytics — pedir permissão que não se usa só
# aumenta o atrito na tela de consentimento.
ESCOPO = " ".join(
    [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
)

PORTA_AUTH = 8765
REDIRECT_URI = f"http://localhost:{PORTA_AUTH}"

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


def url_autorizacao(client_id: str, estado: str) -> str:
    """URL da tela de consentimento do Google para este canal."""
    return AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": ESCOPO,
            "access_type": "offline",
            "prompt": "consent",
            "state": estado,
        }
    )


def _renovar_access_token(cfg: Config) -> str:
    resposta = requests.post(
        TOKEN_URL,
        data={
            "client_id": cfg.youtube_client_id,
            "client_secret": cfg.youtube_client_secret,
            "refresh_token": cfg.youtube_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=60,
    )
    if resposta.status_code != 200:
        raise RuntimeError(
            f"Falha ao renovar o token do YouTube ({resposta.status_code}): "
            f"{resposta.text[:300]}"
        )
    return resposta.json()["access_token"]


def _credenciado(cfg: Config) -> bool:
    return bool(
        cfg.youtube_client_id and cfg.youtube_client_secret and cfg.youtube_refresh_token
    )


def ultimos_publicados(cfg: Config, n: int = 20) -> list[dict]:
    """Últimos vídeos do canal, para o roteiro de hoje não repetir o de ontem.

    Diferente do automacao-video, falha aqui NÃO aborta: lá a lista é a régua da
    escolha da pauta, aqui é só um antídoto contra repetição. Ficar sem ela
    piora um pouco a variedade do dia; abortar custaria o vídeo inteiro.
    """
    if not _credenciado(cfg):
        print("[youtube] Sem credenciais; roteiro seguirá sem histórico.")
        return []
    try:
        cabecalho = {"Authorization": f"Bearer {_renovar_access_token(cfg)}"}
        canal = requests.get(
            CHANNELS_URL,
            params={"part": "contentDetails", "mine": "true"},
            headers=cabecalho,
            timeout=60,
        )
        canal.raise_for_status()
        itens = canal.json().get("items", [])
        if not itens:
            return []
        uploads = itens[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        lista = requests.get(
            PLAYLIST_ITEMS_URL,
            params={"part": "snippet", "playlistId": uploads, "maxResults": min(n, 50)},
            headers=cabecalho,
            timeout=60,
        )
        lista.raise_for_status()
        videos = [
            {
                "titulo": item.get("snippet", {}).get("title", ""),
                "data": item.get("snippet", {}).get("publishedAt", "")[:10],
            }
            for item in lista.json().get("items", [])
        ]
        print(f"[youtube] {len(videos)} vídeos recentes carregados.")
        return videos
    except Exception as erro:  # noqa: BLE001 — histórico é conveniência, não requisito
        print(f"[aviso] Não deu para ler os vídeos recentes ({erro}); seguindo sem.")
        return []


def publicar(
    cfg: Config, video: Path, titulo: str, descricao: str, tags: list[str]
) -> str:
    """Publica o Short e devolve a URL.

    Qualquer falha ABORTA: terminar com código de sucesso sem ter publicado é a
    pior falha possível num cron — todo o custo gasto e nada no ar, sem alarme.
    O arquivo fica em output/, então dá para subir na mão enquanto se investiga.
    """
    if not _credenciado(cfg):
        raise SystemExit(
            "Credenciais do YouTube ausentes — impossível publicar. Rode "
            f"'python main.py --auth-youtube'. O vídeo está salvo em {video}."
        )

    try:
        token = _renovar_access_token(cfg)
        tamanho = video.stat().st_size
        metadados = {
            "snippet": {
                "title": titulo[:100],
                "description": descricao[:5000],
                "tags": tags or [],
                "categoryId": cfg.youtube_category_id,
            },
            "status": {
                "privacyStatus": cfg.youtube_privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        print(f"[youtube] Publicando '{titulo}' ({cfg.youtube_privacy})...")
        inicio = requests.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/*",
                "X-Upload-Content-Length": str(tamanho),
            },
            data=json.dumps(metadados).encode("utf-8"),
            timeout=60,
        )
        if inicio.status_code != 200:
            raise RuntimeError(
                f"YouTube recusou o início do upload ({inicio.status_code}): "
                f"{inicio.text[:300]}"
            )

        with open(video, "rb") as arquivo:
            envio = requests.put(
                inicio.headers["Location"],
                headers={"Content-Type": "video/*", "Content-Length": str(tamanho)},
                data=arquivo,
                timeout=600,
            )
        if envio.status_code not in (200, 201):
            raise RuntimeError(
                f"Falha no envio ({envio.status_code}): {envio.text[:300]}"
            )

        url = f"https://youtu.be/{envio.json()['id']}"
        print(f"[youtube] Publicado: {url}")
        return url
    except Exception as erro:  # noqa: BLE001 — sucesso sem publicar é falha oculta
        raise SystemExit(
            f"Falha na publicação no YouTube: {erro}. O vídeo está salvo em "
            f"{video} — dá para subir manualmente enquanto investiga."
        ) from erro


def autenticar(cfg: Config) -> None:
    """Consentimento OAuth (uma vez só) e gravação do refresh token no .env."""
    if not (cfg.youtube_client_id and cfg.youtube_client_secret):
        raise SystemExit(
            "Defina YOUTUBE_CLIENT_ID e YOUTUBE_CLIENT_SECRET no .env antes de autenticar."
        )

    print("[youtube] Na tela do Google, escolha a conta do canal Gatinho Cria da Rua.")

    codigo: dict[str, str] = {}
    estado = secrets.token_urlsafe(16)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            codigo["code"] = params.get("code", [""])[0]
            codigo["state"] = params.get("state", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h2>Autorizacao concluida.</h2>"
                "<p>Pode fechar esta aba e voltar ao terminal.</p>".encode("utf-8")
            )

        def log_message(self, *_args) -> None:
            pass

    try:
        servidor = http.server.HTTPServer(("localhost", PORTA_AUTH), Handler)
    except OSError as erro:
        raise SystemExit(
            f"Não foi possível ouvir em {REDIRECT_URI} ({erro}). Feche o que estiver "
            f"usando a porta {PORTA_AUTH} e rode de novo."
        ) from erro

    url = url_autorizacao(cfg.youtube_client_id, estado)
    print(f"[youtube] Abrindo o navegador...\n  Se não abrir, acesse:\n  {url}\n")
    threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    servidor.handle_request()
    servidor.server_close()

    if codigo.get("state") != estado or not codigo.get("code"):
        raise SystemExit("Autorização inválida (state divergente ou código ausente).")

    resposta = requests.post(
        TOKEN_URL,
        data={
            "code": codigo["code"],
            "client_id": cfg.youtube_client_id,
            "client_secret": cfg.youtube_client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=60,
    )
    if resposta.status_code != 200:
        raise SystemExit(
            f"Falha ao obter o token ({resposta.status_code}): {resposta.text[:300]}"
        )

    refresh = resposta.json().get("refresh_token")
    if not refresh:
        raise SystemExit(
            "O Google não retornou refresh_token. Remova o acesso anterior em "
            "https://myaccount.google.com/permissions e tente de novo."
        )

    atualizar_env("YOUTUBE_REFRESH_TOKEN", refresh)
    os.environ["YOUTUBE_REFRESH_TOKEN"] = refresh
    print(
        "[youtube] Refresh token salvo em YOUTUBE_REFRESH_TOKEN no .env.\n"
        "          Copie esse valor para a env var do serviço no Render."
    )
