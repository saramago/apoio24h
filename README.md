Apoio 24H com check-in por duracao, sandbox MB WAY e conversa via OpenAI API.

## O que foi criado

- `index.html`: landing page com botoes de check-in e interface de chat.
- `static/app.js`: fluxo do frontend para iniciar check-in, esperar autorizacao e continuar a conversa.
- `static/styles.css`: visual do site.
- `server.py`: servidor local em Python que serve o site e faz proxy para a OpenAI.
- `prompts/advisor_system.txt`: prompt principal para definires o teu guiao.

## Como arrancar

1. Criar um ficheiro `.env` local a partir do exemplo:

```bash
cp .env.example .env
```

2. Editar `.env` e preencher os segredos locais:

- `OPENAI_API_KEY`
- `SIBS_CLIENT_ID`
- `SIBS_CLIENT_SECRET`
- `SIBS_BEARER_TOKEN`
- `SIBS_TERMINAL_ID`

3. Carregar as variaveis no terminal:

```bash
set -a
source .env
set +a
```

Valores suportados:

- `mock`: sandbox local. O pagamento e autorizado automaticamente apos alguns segundos.
- `deeplink`: abre `mbway://send?...` no dispositivo.
- `sibs_sandbox`: usa checkout real + MB WAY purchase + status query na sandbox SIBS.

Para `sibs_sandbox`, define tambem:

O fluxo real da SIBS pede o numero MB WAY do cliente no momento do check-in. O browser nao consegue descobrir esse numero automaticamente.

4. Iniciar o servidor:

```bash
python3 server.py
```

5. Abrir no browser:

```text
http://localhost:8000
```

## Deploy simples

O projeto pode ser publicado como um unico servico Python no Render, servindo frontend e API ao mesmo tempo.

Ficheiro incluído:

- `render.yaml`

No Render, define as env vars reais:

- `OPENAI_API_KEY`
- `MBWAY_MODE`
- `SIBS_CLIENT_ID`
- `SIBS_CLIENT_SECRET`
- `SIBS_BEARER_TOKEN`
- `SIBS_TERMINAL_ID`

## Personalizar o comportamento

Edita `prompts/advisor_system.txt` com o teu prompt advisory. O servidor lê este ficheiro a cada pedido, por isso podes ajustar o texto e voltar a testar sem recompilar nada.

## Seguranca de credenciais

- `.env` esta ignorado pelo Git e nao deve ser publicado.
- `.env.example` serve apenas de molde sem segredos reais.
- Se uma chave aparecer em screenshot, chat, notas ou commits, roda-a imediatamente.

## Nota sobre a sandbox MB WAY

Documentacao usada para o fluxo real:

- `POST /payments` com `Authorization: Bearer ...`
- `POST /payments/{transactionID}/mbway-id/purchase` com `Authorization: Digest {transactionSignature}`
- `GET /payments/{transactionID}/status` com `Authorization: Bearer ...`

## Nota importante

Este projeto e um prototipo de apoio conversacional com IA. Nao deve ser apresentado como substituto de psicoterapia, diagnostico ou resposta a crises.
