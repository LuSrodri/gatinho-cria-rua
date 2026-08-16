# Gatinho Cria da Rua

Automação do canal [@GatinhoCriaDaRua](https://www.youtube.com/@GatinhoCriaDaRua).
Cada execução gera e publica **um Short de 31 segundos que dá a volta em loop**.

## A ideia

Um gato laranja de rua, adolescente, de um bairro arborizado da periferia de São
Paulo. Ele acorda no fim da tarde, toma um café na laje, chama o amigo **Black**
(gato preto, simpático, sempre negociando alguma coisa), passa a noite no rolê e
pega o busão para a escola quando o sol nasce. Todo dia.

O vídeo é o **story que ele postou**: 16 fotos tiradas por ele — ou selfie de
pata esticada, ou foto que ele bateu de outros gatos —, com legenda de story em
cima e uma barra de stories correndo no topo.

A rotina é fixa de propósito: é o que dá formato reconhecível ao canal. O que
muda todo dia são o gancho da primeira foto, os quatro beats do rolê e o que
`variacao.py` sorteia.

### A primeira foto é um gancho

A foto de abertura tem **um segundo** e uma função só dela: impedir que a pessoa
role o feed. O público é dono de gato, e o que faz dono de gato parar não é foto
bonita de gato — é reconhecer o próprio gato. Então ela nunca é "ele acordando":
é ele acordando numa situação absurda de gato, sorteada da lista `GANCHOS` em
`variacao.py` (dormindo numa caixa pequena demais e transbordando dos lados,
sentado exatamente dentro do quadrado de sol da janela, de pernas para o ar no
degrau). O comentário que se quer embaixo do vídeo é "meu gato faria isso".

O sorteio é em Python, e não um "seja criativo" no prompt, pelo mesmo motivo de
todo o resto de `variacao.py`: pedir criatividade a um LLM devolve a média dele,
que aqui é gato fofo dormindo ao sol.

### O ritmo é contado pela história

As fotos **não duram todas o mesmo tempo**. A primeira dura 1s cravado; as
outras quinze duram entre 1,3s e 3,5s, e quem decide é o roteiro: cada cena volta
do `gpt-5.6-luna` com um campo `ritmo` (`corrida`, `normal`, `demorada`,
`longa`), e `config.montar_ritmo` encaixa as durações pretendidas nos 30s que
sobram, por bisseção, respeitando o piso e o teto.

Antes eram 2s cravados para todas. O problema de 2s cravados não é a duração, é a
**regularidade**: um corte exatamente a cada dois segundos, dezesseis vezes, vira
metrônomo — o olho aprende o intervalo em três fotos e passa a esperar o próximo
corte em vez de olhar a foto. Com o ritmo irregular, a foto que carrega a piada
do rolê fica o tempo de a piada acontecer, as fotos de passagem passam mesmo, e o
espectador não consegue prever a próxima virada.

O total continua **fixo em 31s**: a trilha é encomendada com esse tamanho antes
de o vídeo existir, e o loop de áudio depende de saber a duração exata de
antemão. O que a história decide é como repartir os 31s, não quantos são.

### A escala de plano

Ritmo de corte sozinho não faz ritmo visual. O enquadramento estava congelado
dentro dos blocos de `imagens.py`: **toda** selfie era "low angle, close to his
face" e **toda** foto de outros era "from a short distance". Dezesseis fotos,
duas distâncias — o vídeo era slideshow por construção, e variar a duração dos
cortes não podia consertar isso, porque o problema não era o tempo. Ritmo visual
é contraste de escala: o olho tem que reajustar a cada corte, e é o reajuste que
dá a sensação de montagem.

São oito enquadramentos em três famílias, sorteados em `variacao.py`:

| família | enquadramentos |
|---|---|
| fechado | macro no olho (a rua inteira refletida nele), close no rosto |
| médio | plano médio, o gato inteiro, **contra-plongée** (celular no chão, ele grande contra o céu e os fios), de cima |
| aberto | **plano aberto** do lugar, panorâmica do alto |

Três garantias, e cada uma existe porque sem ela o sorteio devolve slideshow:

1. **a família nunca se repete de uma foto para a seguinte.** É a regra que faz o
   trabalho — dois planos médios diferentes seguidos ainda são duas fotos do
   mesmo tamanho;
2. **macro, aberto e contra-plongée aparecem sempre**, um em cada terço do vídeo.
   Sorteio livre às vezes devolvia dezesseis fotos entre médio e close, que é
   justamente a média de onde se está saindo;
3. os enquadramentos que **não cabem numa selfie** (a pata não alcança o celular
   a essa distância) viram foto de outros, e o roteirista é avisado de escrever
   aquele beat pelo lado do que ele está vendo.

A média por vídeo fica em ~5 planos fechados, ~7 médios e ~3,5 abertos: o rosto
dele continua na tela na maior parte do tempo, que é o que um canal de
personagem não pode perder.

O **movimento de câmera anda junto com a escala**, e não é enfeite: a mesma
amplitude de pan que respira num plano aberto vira tremor num macro do olho,
porque no macro cada pixel de deslocamento é muito mais campo de visão. Cada
enquadramento traz seu multiplicador (0,35 no macro, 1,4 na panorâmica).

O roteirista recebe o enquadramento de cada beat como **fato dado**, junto da
lista de beats, e escreve a cena *para* aquela escala. Isso muda bastante o que
ele escreve: num macro do olho não cabe "ele atravessa a rua", cabe o reflexo da
rua no olho dele; num plano aberto não cabe a expressão da cara dele, cabe a rua
e a hora do dia.

### As duas fronteiras

O formato inteiro sai de tratar duas fronteiras de maneiras opostas.

**A fronteira entre fotos é para ser vista.** O corte é seco, a legenda troca no
mesmo quadro (sem `\fad`), a câmera recomeça em outra direção e uma divisão nova
acende na barra do topo. É o que segura os 31s: dezesseis viradas de página, em
intervalos que o espectador não consegue antecipar.

**A fronteira do vídeo é para não ser vista.** O Short reinicia sozinho, então o
corte mais importante é o do último quadro para o primeiro — e é o único que o
espectador vê duas vezes. Nada anuncia o fim:

- o **áudio não tem fade de saída**, e a trilha é costurada em anel: os 2s finais
  são cruzados por cima do começo dela (em `video.py`), então a amostra seguinte
  à última é a primeira. Fazer isso soar como loop de verdade deu bem mais
  trabalho do que parece — ver [A trilha dá a volta](#a-trilha-dá-a-volta);
- o **roteiro não se despede**. O beat 16 é o busão para a escola e o beat 1 é
  ele acordando: são vizinhos, não pontas. O prompt proíbe "até amanhã", resumo
  do dia e qualquer fecho;
- a **primeira foto dura 1s**, metade das outras. Na volta do loop ela atravessa
  depressa o território já conhecido e devolve o vídeo ao movimento antes de dar
  tempo de reconhecer que ele recomeçou.

## Como funciona

```
variacao.sortear             o tempero de hoje: gancho, tempo, humor, visita
        ↓                    e a escala de plano de cada foto
youtube.ultimos_publicados   o que já foi ao ar, para o rolê de hoje não repetir
        ↓
roteiro.gerar_roteiro        gpt-5.6-luna escreve os 16 beats, as 16 legendas
        ↓                    e o ritmo de cada foto
config.montar_ritmo          o ritmo vira segundos, e os segundos viram quadros
variacao.sortear_movimentos  o movimento de câmera, que depende dos dois
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

Então `variacao.py` sorteia, antes de qualquer chamada de API, o gancho da
primeira foto, o tempo que faz hoje, a época do ano no bairro, o humor dele, a
forma do rolê, um "tempero" que atravessa as 16 fotos, quem do elenco recorrente
aparece, quantas fotos são selfie, a escala de plano de cada foto e o movimento
de câmera de cada foto. Isso
entra no prompt como **fato dado**, não como opção — dar a escolha de volta ao
modelo desfaz o sorteio.

O movimento de câmera é sorteado em **taxa por segundo e por escala de plano**,
não em amplitude por foto: com as fotos durando de 1s a 3,5s, a mesma amplitude
de zoom seria três vezes mais rápida numa do que na outra — e velocidade de zoom
é exatamente o que separa respiração de efeito. Por isso ele é o único item que não sai de
`sortear`: só existe depois que o roteiro definiu o ritmo, e é preenchido por
`sortear_movimentos` (com uma corrente de sorteio própria, para partir o sorteio
em dois não mudar o resto).

O esqueleto nunca é sorteado: os 16 beats, a estética, a voz, o gato, o Black e
a trilha. É a constância que faz o canal ser reconhecível; o sorteio mexe só no
recheio.

A semente é `data-hora` do run, então as quatro execuções do dia saem diferentes
e um run é reproduzível — a semente vai no log.

### A barra de stories

Com 16 divisões ela também virou marcador de corte: cada foto acende uma divisão
nova, então a fronteira entre duas fotos aparece no topo da tela mesmo quando as
duas imagens têm enquadramento parecido.

As divisões são todas do **mesmo tamanho**, embora as fotos durem de 1s a 3,5s. É
de propósito, e virou uma escolha bem maior do que era: a barra é a régua do
formato (dezesseis fotos, sempre), não do tempo. Divisões proporcionais à duração
denunciariam a foto longa antes de ela chegar — o espectador veria que vem coisa
boa, e a surpresa é metade do efeito. O que muda de uma divisão para a outra é só
a velocidade com que ela enche.

Ela fica **60px mais abaixo** e com margem lateral, e as duas coisas são a mesma
ideia: colada no alto e quase encostando nas bordas, ela lia como um elemento do
player — uma barra de progresso do YouTube desenhada no lugar errado. Descida e
recuada, com a faixa vazia acima fazendo o papel da barra de status, ela lê como
a interface de story de um celular. O @ do canal é alinhado à esquerda dela: um
cabeçalho com dois alinhamentos diferentes é a primeira coisa que entrega que a
interface é desenhada.

O preenchimento de cada divisão é feito em degraus com `enable`, não com uma
largura em função de `t`. Motivo: o `drawbox` do ffmpeg resolve `w` uma única
vez, na inicialização — só o `enable` é reavaliado quadro a quadro. O número de
degraus é calculado por divisão para cada degrau durar ~0,1s, que é o limiar em
que o preenchimento deixa de se ver pular; com um número fixo, o degrau da foto
de 3,5s seria quase três vezes o da foto de 1,3s e só um dos dois seria
imperceptível.

São dezenas de degraus × 16 fotos, e o filtergraph passa de 30 mil caracteres —
mais do que cabe numa linha de comando do Windows. Por isso ele vai num arquivo,
com `-filter_complex_script`.

### As legendas

Caixa de story do Instagram: fundo preto translúcido, texto branco, um retângulo
por linha (`BorderStyle: 3` do ASS). Uma legenda por foto, entrando e saindo em
corte seco junto com ela — a legenda é o marcador de corte mais visível que o
vídeo tem.

Elas ficam no **terço central** da tela, e não no inferior: é onde o olho já
está quando a foto troca, e o terço inferior ainda disputa espaço com o título, o
@ e os botões que o próprio YouTube desenha por cima do Short.

O corpo cheio é 89px (era 76px), e a regra de quebra é **uma linha ganha de
duas**: se a frase não cabe em 89px, o corpo é reduzido até 76px atrás de uma
linha só, e só então ela quebra. O piso é exatamente o corpo antigo, ou seja,
nenhuma legenda ficou menor do que já era. Aumentar a fonte e reduzir as quebras
são pedidos que brigam entre si — a 89px cabem umas 19 letras por linha, e a
legenda média do canal tem 20 —, e é essa regra que atende os dois: medido num
vídeo de teste, as quebras caíram de 9 em 16 para 2 em 16.

Quando a quebra é inevitável, o ponto de corte é o que deixa as **duas linhas
mais parecidas**. Quebra gulosa produz uma linha cheia e uma palavra órfã
embaixo, e órfã lê como erro de montagem.

`WrapStyle: 2` desliga a quebra automática do libass: a linha só quebra onde
`legendas.py` escreveu `\N`. Só é seguro porque a medição usa a mesma fonte, no
mesmo corpo, e `PlayResX` é a largura real do vídeo — o que a Pillow mede é o que
o libass desenha. E a largura útil desconta o respiro que o `BorderStyle: 3`
desenha em volta do texto, que a versão anterior ignorava (era metade das
quebras desnecessárias).

### A trilha dá a volta

Pedir um loop à ElevenLabs **não produz um loop**, por mais explícito que seja o
prompt. Duas coisas voltam erradas, e as duas foram medidas montando o anel de
áudio e tocando o resultado duas vezes seguidas:

- **o andamento não fecha em compasso inteiro.** O prompt pede ~75 BPM e a faixa
  veio a ~99; a 99 BPM o compasso dura 2,41s, e 31 segundos são 12,84 compassos.
  Não 13. Aí o cruzamento não salva nada, ele só muda de lugar o estrago:
  enquanto a volta toca, a batida vem certa, porque a volta é a continuação do
  que estava tocando; quando ela se apaga e o corpo assume, a grade do corpo está
  fora de fase e a batida tropeça. A medida que diz isso em um número: o laço
  precisa ter um número inteiro de pulsos, e o do anel dava 51,35 — um terço de
  pulso fora;
- **um segundo e meio de silêncio digital no fim**, abaixo de -55 dBFS. E é
  justamente o fim da trilha que é cruzado por cima do começo dela. Quando o
  silêncio cai no começo do cruzamento, a música afunda para 0,73x da energia
  normal e uma batida some.

Como nenhuma das duas se resolve no prompt, a trilha é pedida **8 segundos mais
longa** do que se vai usar, e `musica.py` faz o resto: acha as bordas reais do
som, recorta do miolo da faixa (longe da introdução e da resolução) e estica o
andamento com `atempo` o tanto que faltar para os 31s darem um número inteiro de
compassos — 1,3% na faixa real, inaudível. O laço vai de 51,35 pulsos para
52,01 — menos de um centésimo de pulso fora do inteiro.

O compasso é medido por autocorrelação do envelope de ataque, com a stdlib e
nada mais, em dois passos: o primeiro acha o pulso com a precisão grosseira de um
quadro de envelope, e o segundo procura o pico no múltiplo mais alto do pulso que
ainda cabe na faixa e divide — o mesmo erro de medida, dividido por dezesseis.
Isso importa porque a correção é de 1,3% e a medida grosseira erra 2%: sem o
refinamento, estaria corrigindo com ruído.

Errar o compasso por uma oitava quase não muda o resultado: o que se pede à
unidade encontrada é caber um número inteiro de vezes em 31s, e um múltiplo do
compasso cabe inteiro exatamente quando o compasso cabe.

### A trilha entra duas vezes, e não é desperdício

O anel da trilha pede o mesmo áudio em dois pontos: o corpo do vídeo e a volta
do loop. O caminho natural é uma entrada só, `asplit` em dois ramos e um
`acrossfade` juntando — uma linha. **Isso monta no ffmpeg 8.1.1 e falha no 7.1**,
que é o que o `python:3.12-slim` instala, com `Could not open encoder before EOF`:
a cadeia de áudio não entrega um único quadro e o encoder AAC morre sem nunca
saber o formato.

O motivo é que o `acrossfade` só emite depois de ler a primeira entrada inteira,
e a primeira entrada é o *fim* do arquivo — para chegar lá, o `asplit` precisa
empurrar 31s pelo outro ramo, que ninguém está consumindo. O 8.1.1 tolera o
acúmulo; o 7.1 desiste.

Por isso a trilha entra como duas entradas independentes e o cruzamento é feito
com `amix`, que consome os dois ramos em paralelo, com `normalize=0` para ele
somar sem reescalar.

Se for mexer nisto, teste no ffmpeg da imagem, não no da sua máquina.

### Dois detalhes de áudio que só aparecem no arquivo pronto

**A curva do cruzamento é `qsin`, não a `tri` linear.** Ganho linear é o certo
quando os dois lados são o mesmo som — a soma reconstrói o original. Mas os dois
lados aqui são a mesma faixa em pontos diferentes dela, treze compassos de
distância: dois sinais diferentes não somam amplitude, somam potência, e no meio
do cruzamento (0,5 + 0,5) a potência cai pela metade. Medido no anel, a energia
do cruzamento caía para 0,70x a do resto. Com `qsin` é a soma dos quadrados que
dá 1, a potência fica constante, e a mesma medida dá 0,97x.

**A faixa de áudio termina 1,4ms antes do vídeo.** O AAC codifica em blocos de
1024 amostras e completa com zeros o bloco que sobrar: 31s a 44.100 Hz são
1335,06 blocos, e os 964 zeros do bloco incompleto viravam 19ms de silêncio
digital no fim do arquivo — exatamente entre a última amostra e a primeira, que é
o único lugar onde ele não pode ficar. Isso só aparece decodificando o `.mp4`
pronto: não está na trilha, nem no filtro, nem no log do ffmpeg.

Não dá para alinhar as três coisas: uma duração múltipla de 1/30 de segundo *e*
de 1024/44100 tem que ser múltipla de 17,067s, e 31 não é. Então o vídeo fica com
os 31s cravados e o áudio é encurtado até o bloco fechado anterior. Encurtar, e
não esticar até o bloco seguinte: esticando, o áudio fica mais longo que o vídeo,
o `-frames:v` encerra a saída no último quadro de imagem e apara a faixa de volta
para um tamanho que não é nenhum dos dois. Ficando abaixo, o que sai é exatamente
o que está escrito no `config.py`.

`DUR_AUDIO`, e não `DUR_TOTAL`, é a duração real do laço — é a ela que
`musica.py` alinha os compassos.

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
