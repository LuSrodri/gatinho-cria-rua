# Gatinho Cria da Rua

Automação do canal [@GatinhoCriaDaRua](https://www.youtube.com/@GatinhoCriaDaRua).
Cada execução gera e publica **um Short de 31 segundos que dá a volta em loop**.

## A ideia

Um gato laranja de rua, adolescente, de um bairro arborizado da periferia de São
Paulo. Ele acorda no fim da tarde, toma um café na laje, chama o amigo **Black**
(gato preto, simpático, sempre negociando alguma coisa), passa a noite no rolê e
pega o busão para a escola quando o sol nasce. Todo dia.

O vídeo é o **story que ele postou**: 16 fotos tiradas por ele — ou selfie de
pata esticada, ou foto que ele bateu de outros gatos —, 2 segundos cada (a
primeira 1s), com legenda de story em cima e uma barra de stories correndo no
topo.

A rotina é fixa de propósito: é o que dá formato reconhecível ao canal. O que
muda todo dia são os quatro beats do rolê e o que `variacao.py` sorteia.

### As duas fronteiras

O formato inteiro sai de tratar duas fronteiras de maneiras opostas.

**A fronteira entre fotos é para ser vista.** A cada 2s o corte é seco, a legenda
troca no mesmo quadro (sem `\fad`), a câmera recomeça em outra direção e uma
divisão nova acende na barra do topo. É o que segura os 31s: dezesseis viradas
de página em vez de oito quadros esperando o próximo.

**A fronteira do vídeo é para não ser vista.** O Short reinicia sozinho, então o
corte mais importante é o do último quadro para o primeiro — e é o único que o
espectador vê duas vezes. Nada anuncia o fim:

- o **áudio não tem fade de saída**. A trilha é pedida à ElevenLabs com
  `DUR_TOTAL + CAUDA_LOOP` de duração, e os 2s de sobra são cruzados por cima do
  começo dela (`acrossfade`, em `video.py`). A amostra seguinte à última é a
  primeira, sem degrau — a música dá a volta em vez de terminar;
- o **roteiro não se despede**. O beat 16 é o busão para a escola e o beat 1 é
  ele acordando: são vizinhos, não pontas. O prompt proíbe "até amanhã", resumo
  do dia e qualquer fecho;
- a **primeira foto dura 1s**, metade das outras. Na volta do loop ela atravessa
  depressa o território já conhecido e devolve o vídeo ao movimento antes de dar
  tempo de reconhecer que ele recomeçou.

## Como funciona

```
variacao.sortear             o tempero de hoje: tempo, humor, visita, movimento
        ↓
youtube.ultimos_publicados   o que já foi ao ar, para o rolê de hoje não repetir
        ↓
roteiro.gerar_roteiro        gpt-5.6-luna escreve os 16 beats e as 16 legendas
        ↓
imagens.gerar_imagens        gpt-image-2 gera as 16 fotos ┐ em paralelo: as duas
musica.gerar_musica          ElevenLabs compõe a trilha   ┘ esperas são de rede
        ↓
legendas.gerar_legendas      o .ass das caixas de story
        ↓
video.montar_video           ffmpeg monta os 31s num passe só
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

Os coadjuvantes (o Black e o convidado do dia) não têm referência commitada,
então a primeira foto em que cada um aparece é gerada **antes** das outras e
vira a referência dele no resto da execução — por isso a geração acontece em
duas ondas.

### A estética: periferia bonita

A versão anterior pedia "celular barato, ruído de sensor, foco mole" atrás de
autenticidade, num cenário de tijolo cru e laje precária. O que chegava era foto
feia, e feia não retém ninguém.

Duas correções, em `imagens.py`:

- **o celular é bom.** Autenticidade vem do enquadramento (torto, na correria,
  de baixo), não da qualidade ruim. Celular bom + mão de amador dá foto de story
  bonita;
- **o bairro é bonito.** Rua arborizada com ipê florido, casa pintada, jardim,
  samambaia na varanda, laje com horta, calçada de pedra portuguesa, mural de
  artista do bairro. Continua periferia — laje, portão, grade, fio de poste —,
  mas a versão cuidada dela, que é a que a maior parte dela realmente é.

### A variedade é sorteada em Python, não pedida ao modelo

Quatro vídeos por dia com a mesma rotina viram o mesmo vídeo quatro vezes. Mas
pedir "seja criativo" a um LLM devolve a média dele, que é justamente o
lugar-comum.

Então `variacao.py` sorteia, antes de qualquer chamada de API, o tempo que faz
hoje, a época do ano no bairro, o humor dele, a forma do rolê, um "tempero" que
atravessa as 16 fotos, quem do elenco recorrente aparece, quantas fotos são
selfie e o movimento de câmera de cada foto. Isso entra no prompt como **fato
dado**, não como opção — dar a escolha de volta ao modelo desfaz o sorteio.

O movimento de câmera é sorteado em **taxa por segundo**, não em amplitude por
foto: a mesma amplitude em 2s é o dobro da velocidade que era em 4s, e o dobro
da velocidade é onde o Ken Burns deixa de parecer respiração e passa a parecer
efeito. Por isso `sortear` recebe as durações, e não a quantidade de fotos.

O esqueleto nunca é sorteado: os 16 beats, a estética, a voz, o gato, o Black e
a trilha. É a constância que faz o canal ser reconhecível; o sorteio mexe só no
recheio.

A semente é `data-hora` do run, então as quatro execuções do dia saem diferentes
e um run é reproduzível — a semente vai no log.

### A barra de stories

Com 16 divisões ela também virou marcador de corte: cada foto acende uma divisão
nova, então a fronteira entre duas fotos aparece no topo da tela mesmo quando as
duas imagens têm enquadramento parecido. As divisões são todas do mesmo tamanho,
embora a primeira foto dure metade das outras — a barra é a régua do formato,
não do tempo, e uma divisão pela metade seria lida como defeito.

O preenchimento de cada divisão é feito em degraus com `enable`, não com uma
largura em função de `t`. Motivo: o `drawbox` do ffmpeg resolve `w` uma única
vez, na inicialização — só o `enable` é reavaliado quadro a quadro. Com 20
degraus por divisão (~3px cada, ~0,1s cada), a 30fps não se distingue de um
preenchimento contínuo.

São 20 degraus × 16 fotos, e o filtergraph passa de 30 mil caracteres — mais do
que cabe numa linha de comando do Windows. Por isso ele vai num arquivo, com
`-filter_complex_script`.

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
