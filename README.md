# Gatinho Cria da Rua

Automação do canal [@GatinhoCriaDaRua](https://www.youtube.com/@GatinhoCriaDaRua).
Cada execução gera e publica **um Short de 20 segundos**.

## A ideia

Um gato laranja de rua, adolescente, da periferia de São Paulo. Ele acorda no
fim da tarde, toma um café na laje, chama o amigo **Black** (gato preto,
simpático, sempre negociando alguma coisa), passa a noite no rolê e pega o busão
para a escola quando o sol nasce. Todo dia.

O vídeo é o **story que ele postou**: 8 fotos tiradas por ele — ou selfie de
pata esticada, ou foto que ele bateu de outros gatos —, 2,5 segundos cada, com
legenda de story em cima e uma barra de stories correndo no topo.

A rotina é fixa de propósito: é o que dá formato reconhecível ao canal. O que
muda todo dia são os três beats do rolê.

## Como funciona

```
youtube.ultimos_publicados   o que já foi ao ar, para o rolê de hoje não repetir
        ↓
roteiro.gerar_roteiro        gpt-5.6-luna escreve os 8 beats e as 8 legendas
        ↓
imagens.gerar_imagens        gpt-image-2 gera as 8 fotos  ┐ em paralelo: as duas
musica.gerar_musica          ElevenLabs compõe a trilha   ┘ esperas são de rede
        ↓
legendas.gerar_legendas      o .ass das caixas de story
        ↓
video.montar_video           ffmpeg monta os 20s num passe só
        ↓
youtube.publicar             sobe o Short
```

### O gato tem que ser o mesmo gato

É o problema difícil do projeto: um canal de personagem morre quando o
espectador percebe que o gato de cada foto é outro gato.

`assets/estetica.png` está commitada no repositório e entra como imagem de
referência em **todas** as chamadas ao `gpt-image-2` (`images.edit` aceita uma
lista de referências e processa todas em alta fidelidade). Ela define o gato
laranja e a estética do canal.

O Black não tem referência commitada, então a foto em que ele aparece primeiro é
gerada **antes** das outras e vira a referência dele no resto da execução — por
isso a geração acontece em duas ondas.

### A barra de stories

O preenchimento de cada divisão é feito em degraus com `enable`, não com uma
largura em função de `t`. Motivo: o `drawbox` do ffmpeg resolve `w` uma única
vez, na inicialização — só o `enable` é reavaliado quadro a quadro. Com 25
degraus por divisão (~5px cada), a 30fps não se distingue de um preenchimento
contínuo.

## Rodando

```bash
pip install -r requirements.txt
cp .env.example .env      # preencha as chaves

python main.py --auth-youtube   # uma vez: autoriza o canal no YouTube
python main.py --sem-publicar   # gera e para, para conferir o arquivo
python main.py                  # gera e publica
```

Precisa de `ffmpeg` no PATH (o `Dockerfile` já instala).

O vídeo sai em `output/`, e cada publicação vira uma entrada em `videos.txt`.
Os dois são locais: no Render o contêiner é descartado no fim de cada execução,
então o histórico que vale lá é o do próprio canal (que `ultimos_publicados` lê
da API) e os logs do serviço.

## Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `OPENAI_API_KEY` | roteiro (`gpt-5.6-luna`) e fotos (`gpt-image-2`) |
| `ELEVENLABS_API_KEY` | trilha instrumental (`POST /v1/music`) |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | credencial OAuth do projeto no Google Cloud |
| `YOUTUBE_REFRESH_TOKEN` | o canal autorizado; preenchido por `--auth-youtube` |

O resto tem padrão e está listado em `.env.example`.

As credenciais OAuth podem ser as mesmas do `automacao-video`: o que separa um
canal do outro é o **refresh token**, não o client.

## Falhas: o que derruba e o que não derruba

Um cron que termina com código de sucesso sem ter publicado é a pior falha
possível — gastou tudo e não avisou ninguém. Então:

| Falha | O que acontece |
|---|---|
| Roteiro, imagens, ffmpeg ou publicação | **aborta** a execução com erro |
| Trilha da ElevenLabs | avisa e segue; o vídeo sai com faixa silenciosa |
| Leitura dos vídeos recentes | avisa e segue; o roteiro perde só o antirrepetição |

Quando a publicação falha, o `.mp4` já está em `output/` e dá para subir na mão.

## Deploy

Docker, num Cron Job do Render, 4 vezes por dia no horário de Brasília.
Autodeploy no push da `main`.

## Licenças

Fontes Poppins (`fonts/`) sob SIL Open Font License 1.1.
