# crypto-etl-pipeline

Pipeline ETL em Python que extrai preços de criptomoedas de uma API pública, valida os dados e os carrega em PostgreSQL de forma **idempotente** e **incremental**.

> **Status:** em desenvolvimento. O planejamento está concluído e a implementação segue por marcos (veja o [Roadmap](#roadmap)). As seções de uso descrevem o comportamento **previsto** e serão ajustadas conforme cada marco for entregue.

## Sobre

Projeto pessoal de estudo em engenharia de dados. O objetivo é praticar, em um caso realista, os fundamentos de um pipeline ETL:

- consumo de API com retry e backoff;
- transformação com funções puras e testáveis;
- validação de qualidade com regras combináveis;
- carga idempotente com SQLAlchemy, transações e rollback;
- execução incremental, logging estruturado e agendamento.

## Funcionalidades

- Extração de preços de uma API pública de criptomoedas (3 a 5 ativos).
- Dois modos de carga: histórico inicial (backfill) e snapshots periódicos.
- Armazenamento do JSON bruto em disco antes de qualquer transformação, permitindo reprocessar sem chamar a API novamente.
- Validação com três desfechos: registro válido, **suspeito** (sinalizado) ou **rejeitado** (com motivo).
- Upsert por `(asset_id, ts)`: executar duas vezes seguidas produz o mesmo resultado.
- Carga incremental por *watermark* de cada ativo.
- Segundo formato de entrada (CSV histórico) processado pela mesma estrutura.
- Registro de cada execução com contagens de lidos, válidos, suspeitos e rejeitados.

## Arquitetura

```
API / CSV ──> raw (JSON em disco) ──> transform ──> validate ──> load (PostgreSQL)
                                                       │
                                                       └──> rejected_records
```

Cada etapa é um módulo com uma única responsabilidade, e o `pipeline` apenas orquestra e registra a execução.

## Modelo de dados

| Tabela | Conteúdo | Chave única |
|---|---|---|
| `prices` | `asset_id`, `ts` (timestamptz, UTC), `price_usd`, `market_cap`, `volume`, `status` (`ok` ou `suspeito`), `run_id` | `(asset_id, ts)` |
| `rejected_records` | registro original, regra violada, motivo, `run_id`, data | id próprio |
| `etl_runs` | `run_id`, início, fim, fonte, lidos, válidos, suspeitos, rejeitados, status final, erro | `run_id` |
| `watermarks` | `asset_id`, último `ts` carregado | `asset_id` |

## Regras de validação

| Regra | Ação |
|---|---|
| Campos obrigatórios nulos | Rejeitar |
| Preço menor ou igual a zero | Rejeitar |
| Tipo inválido (valor não numérico) | Rejeitar |
| `(asset_id, ts)` duplicado no lote | Rejeitar o excedente |
| Timestamp no futuro | Rejeitar |
| Variação brusca entre pontos consecutivos acima de um limite configurável | Sinalizar como `suspeito` |

Um registro inválido nunca interrompe o lote: ele vai para `rejected_records` e o processamento continua.

## Tecnologias

- Python 3.11 ou superior
- PostgreSQL (via Docker)
- SQLAlchemy
- pandas (apenas se necessário na transformação)
- pytest e ruff
- cron para agendamento

## Estrutura do projeto

```
crypto-etl-pipeline/
├── src/etl/
│   ├── extract.py       # API (paginação, retry, backoff) e leitura de CSV
│   ├── transform.py     # bruto -> linhas com schema fixo (funções puras)
│   ├── validate.py      # regras de qualidade
│   ├── load.py          # upsert idempotente em transação
│   ├── models.py        # tabelas SQLAlchemy
│   ├── config.py        # leitura do .env
│   └── pipeline.py      # orquestração E -> T -> V -> L
├── tests/
├── data/raw/            # JSON bruto (ignorado pelo Git)
├── logs/                # logs de execução (ignorado pelo Git)
├── docker-compose.yml
├── .env.example
├── pyproject.toml
└── README.md
```

## Como executar

### Pré-requisitos

- Python 3.11+
- Docker e Docker Compose
- Git

### Instalação

```bash
git clone https://github.com/math-antero/crypto-etl-pipeline.git
cd crypto-etl-pipeline

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

### Configuração

```bash
cp .env.example .env
```

Edite o `.env` com os seus valores. **Nunca versione o `.env`.**

| Variável | Descrição | Exemplo |
|---|---|---|
| `DATABASE_URL` | String de conexão com o PostgreSQL | `postgresql+psycopg://usuario:senha@localhost:5432/crypto_etl` |
| `API_KEY` | Chave da API, se a fonte exigir | *(vazio ou a sua chave)* |
| `ASSET_IDS` | Ativos a coletar, separados por vírgula | `bitcoin,ethereum` |
| `RAW_DATA_DIR` | Pasta do JSON bruto | `data/raw` |
| `SPIKE_THRESHOLD` | Variação percentual que marca um ponto como suspeito | `0.20` |
| `LOG_LEVEL` | Nível de log | `INFO` |

### Banco de dados

```bash
docker compose up -d db
```

### Execução (interface prevista)

```bash
# execução padrão (snapshot + incremental)
python -m etl.pipeline

# carga de um CSV histórico
python -m etl.pipeline --source csv --file caminho/para/arquivo.csv
```

### Agendamento

Exemplo de entrada no `crontab` para rodar de hora em hora:

```cron
0 * * * * cd /caminho/para/crypto-etl-pipeline && .venv/bin/python -m etl.pipeline >> logs/cron.log 2>&1
```

### Testes e qualidade

```bash
pytest
ruff check .
```

## Decisões de projeto

- **UTC em tudo.** Todo timestamp é armazenado como `timestamptz` em UTC para evitar erros com fusos horários.
- **Precisão monetária.** Valores usam `Numeric` no PostgreSQL e `Decimal` no Python, nunca `float`.
- **Camada raw.** O JSON bruto é salvo antes de qualquer transformação, para permitir reprocessamento.
- **Idempotência.** A carga usa `INSERT ... ON CONFLICT DO UPDATE` dentro de uma transação, com rollback em caso de erro.
- **Suspeito não é erro.** Cripto é volátil, então variações bruscas são sinalizadas em vez de descartadas.
- **Isolamento de falhas.** Um erro em um ativo não contamina os demais e fica registrado em `etl_runs`.

## Roadmap

- [ ] **M0** Setup: repositório, ambiente virtual, Docker com PostgreSQL, `pytest` e `ruff`
- [ ] **M1** Extract: cliente da API com retry e backoff, JSON bruto em disco
- [ ] **M2** Transform: schema fixo, conversões de tipo e fuso, testes unitários
- [ ] **M3** Load: modelos SQLAlchemy, upsert idempotente em transação
- [ ] **M4** Validação: regras, `rejected_records`, status `suspeito`, relatório por execução
- [ ] **M5** Incremental: *watermarks*, backfill e snapshots, logging estruturado
- [ ] **M6** Acabamento: segundo formato (CSV), linha de comando, cron, documentação
- [ ] **M7** (opcional) Análise em SQL: média móvel, variação diária e correlação com funções de janela

## Limitações e avisos

- Projeto de estudo, sem garantias de uso em produção.
- Os dados vêm de uma API de terceiros e estão sujeitos aos termos de uso e aos limites dela.
- Este repositório trata apenas de engenharia e análise de dados. **Nada aqui constitui recomendação de investimento.**

## Licença

Distribuído sob a licença MIT. Veja o arquivo `LICENSE`.

## Autor

Matheus Antero · [GitHub](https://github.com/math-antero)
