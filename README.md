Apoio 24H com check-in por duracao, sandbox MB WAY e conversa via OpenAI API.

## O que foi criado

- `index.html`: landing page com botoes de check-in e interface de chat.
- `static/app.js`: fluxo do frontend para iniciar check-in, esperar autorizacao e continuar a conversa.
- `static/styles.css`: visual do site.
- `server.py`: servidor local em Python que serve o site e faz proxy para a OpenAI.
- `prompts/advisor_system.txt`: prompt principal para definires o teu guiao.

## Como arrancar

1. Definir a chave da OpenAI:

```bash
export OPENAI_API_KEY="coloca-aqui-a-tua-chave"
```

2. Opcionalmente escolher o modelo:

```bash
export OPENAI_MODEL="gpt-4.1-mini"
```

3. Opcionalmente configurar o modo MB WAY:

```bash
export MBWAY_MODE="mock"
```

Valores suportados:

- `mock`: sandbox local. O pagamento e autorizado automaticamente apos alguns segundos.
- `deeplink`: abre `mbway://send?...` no dispositivo.
- `sibs_sandbox`: deixa a app preparada para futura integracao SIBS sandbox real.

4. Iniciar o servidor:

```bash
python3 server.py
```

5. Abrir no browser:

```text
http://localhost:8000
```

## Personalizar o comportamento

Edita `prompts/advisor_system.txt` com o teu prompt advisory. O servidor lê este ficheiro a cada pedido, por isso podes ajustar o texto e voltar a testar sem recompilar nada.

## Nota sobre a sandbox MB WAY

O portal publico da SIBS confirma que existe registo em SANDBOX para testar as APIs, mas a documentacao tecnica detalhada e credenciais ficam atras do portal de developers. Por isso este repositório inclui uma sandbox local funcional (`MBWAY_MODE=mock`) e uma base para futura ligacao ao modo `sibs_sandbox`.

## Nota importante

Este projeto e um prototipo de apoio conversacional com IA. Nao deve ser apresentado como substituto de psicoterapia, diagnostico ou resposta a crises.
