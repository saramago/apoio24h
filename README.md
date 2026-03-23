# apoio24h.com v1

apoio24h e uma aplicacao web portuguesa de triagem leve e encaminhamento util.

O utilizador escreve ou fala o que precisa. O sistema classifica de forma conservadora e encaminha para recursos adequados. A conversa paga so aparece em situacoes nao urgentes, com primeira resposta curta gratis e continuacao por 1€.

## Escopo desta v1

- pagina inicial minimalista
- triagem com 4 classes:
  - `emergency_potential`
  - `urgent_care`
  - `practical_health`
  - `light_conversation`
- encaminhamento para 112, SNS 24, urgencias, hospitais, medicamentos e mapa
- monetizacao apenas na conversa nao urgente
- painel tecnico minimo de observabilidade

## Arquitetura atual

- `index.html`: interface unica e austera
- `static/app.js`: fluxo do frontend
- `static/styles.css`: UI minimalista
- `server.py`: servidor HTTP, API, admin e servico de ficheiros
- `core/triage_engine.py`: classificacao conservadora
- `core/resource_engine.py`: recursos e encaminhamento
- `core/conversation_engine.py`: resposta curta gratis e conversa paga
- `core/payments_engine.py`: MB WAY mock / SIBS sandbox
- `core/providers/`: abstractions de fontes e mapa
- `core/jobs.py`: refresh jobs simples
- `data/sns_facilities_seed.json`: fallback utilitario para urgencias e hospitais
- `pages/`: paginas factuais curtas
- `tests/`: testes unitarios e de integracao

## Providers

Implementados como abstractions separadas:

- `sns_transparencia`
- `sns_portal`
- `infarmed_infomed`
- `farmacias_provider`
- `maps_provider`

Notas de honestidade:

- `sns_portal`: usado para contactos e links institucionais
- `sns_transparencia`: nesta versao serve uma base utilitaria de fallback para urgencias e hospitais
- `infarmed_infomed`: usado como ponto institucional para medicamentos
- `farmacias_provider`: ainda nao validado para dados robustos de servico; a UI assinala indisponibilidade quando aplicavel
- `maps_provider`: links de pesquisa e rota em mapa externo

## Como arrancar

1. Criar `.env`:

```bash
cp .env.example .env
```

2. Ajustar variaveis no `.env`:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `MBWAY_MODE`
- `ADMIN_TOKEN`

Opcional:

- `SIBS_CLIENT_ID`
- `SIBS_CLIENT_SECRET`
- `SIBS_BEARER_TOKEN`
- `SIBS_TERMINAL_ID`
- `ENABLE_PROVIDER_REFRESH_JOBS`
- `PROVIDER_REFRESH_INTERVAL_SECONDS`

3. Arrancar:

```bash
python3 server.py
```

4. Abrir:

```text
http://localhost:8000
```

## Modos de pagamento

- `mock`: autorizacao automatica apos alguns segundos
- `deeplink`: abre `mbway://send?...`
- `sibs_sandbox`: usa sandbox SIBS se as credenciais estiverem configuradas

## Testes

Executar:

```bash
python3 -m unittest discover -s tests -v
```

Cobertura atual:

- triagem
- recursos
- mock payment
- fluxos principais da API

## Deploy

O projeto pode continuar a correr como um unico servico Python no Render.

Ficheiro incluido:

- `render.yaml`

No Render, define pelo menos:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `MBWAY_MODE`
- `ADMIN_TOKEN`

## Admin observability

Endpoint JSON:

```text
/api/admin/status?token=SEU_TOKEN
```

Pagina HTML:

```text
/admin?token=SEU_TOKEN
```

## Limites reais desta v1

- nao faz diagnostico
- nao substitui SNS 24, 112 ou consulta medica
- nao promete tempos de espera em tempo real
- nao promete farmacias de servico em tempo real sem fonte validada
- usa fallback utilitario quando uma fonte nao estiver validada ou falhar
- a camada de conversa e curta e deliberadamente limitada
