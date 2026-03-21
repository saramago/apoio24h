Apoio 24H com onboarding nominal e conversa via OpenAI API.

## O que foi criado

- `index.html`: landing page com CTA, onboarding e interface de chat.
- `static/app.js`: fluxo do frontend para iniciar sessao e continuar a conversa.
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

3. Iniciar o servidor:

```bash
python3 server.py
```

4. Abrir no browser:

```text
http://localhost:8000
```

## Personalizar o comportamento

Edita `prompts/advisor_system.txt` com o teu prompt advisory. O servidor lê este ficheiro a cada pedido, por isso podes ajustar o texto e voltar a testar sem recompilar nada.

## Nota importante

Este projeto e um prototipo de apoio conversacional com IA. Nao deve ser apresentado como substituto de psicoterapia, diagnostico ou resposta a crises.
