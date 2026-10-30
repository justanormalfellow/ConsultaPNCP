# Ingestão de Dados PNCP

Este projeto realiza a extração, transformação e carga (ETL) de dados de contratações públicas do Portal Nacional de Contratações Públicas (PNCP).

## Tecnologias Utilizadas
- **Python 3.12.8**
- **FastAPI** (para a interface web)
- **PostgreSQL** + **asyncpg** (banco de dados e pool de conexões)
- **httpx** (requisições assíncronas à API do governo)
- **uv** (gerenciamento de pacotes e ambiente virtual)
- **Jinja2** (templates HTML)