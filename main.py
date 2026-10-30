from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import asyncpg
import json, math
from database import db, get_db

# Lifespan: abre o banco quando a API sobe, fecha quando desce
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()

app = FastAPI(lifespan=lifespan)


# Configura a pasta de templates
templates = Jinja2Templates(directory="templates")

# Rota para a página inicial (o formulário)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request): #type: ignore
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/contratacoes", response_class=HTMLResponse)
async def listar_contratacoes(
    request: Request,
    uf: str | None = None,
    palavra_chave: str | None = None,
    valor_minimo: str | None = None,
    limite: int = 10,
    offset: int = 0,
    conn: asyncpg.Connection = Depends(get_db)
):
    # 1. Monta a base da query dinamicamente
    where_clause = "WHERE 1=1"
    params = []
    
    if uf:
        params.append(uf)
        where_clause += f" AND uf = ${len(params)}"
        
    if palavra_chave:
        params.append(f"%{palavra_chave}%")
        where_clause += f" AND dados_brutos->>'objetoCompra' ILIKE ${len(params)}"
        
    if valor_minimo:
        params.append(float(valor_minimo))
        where_clause += f" AND (dados_brutos->>'valorTotalEstimado')::numeric >= ${len(params)}"

    # 2. Query para saber o TOTAL de registros (para calcular as páginas)
    count_query = f"SELECT COUNT(*) FROM pncp_contratacoes {where_clause}"
    total_registros = await conn.fetchval(count_query, *params)

    # 3. Query para pegar os dados da página atual
    # Importante: adicionamos LIMIT e OFFSET aos parâmetros
    query = f"SELECT * FROM pncp_contratacoes {where_clause}"
    
    # Cria uma cópia dos params para não interferir na query de count
    params_paginados = params.copy() 
    params_paginados.extend([limite, offset])
    
    query += f" LIMIT ${len(params_paginados) - 1} OFFSET ${len(params_paginados)}"
    
    registros = await conn.fetch(query, *params_paginados)
    
    # 4. Tratamento dos dados (seu código original)
    dados_formatados = []
    for r in registros:
        item = dict(r)
        item['detalhes'] = json.loads(item['dados_brutos'])
        dados_formatados.append(item)

    # 5. Lógica da Paginação
    pagina_atual = (offset // limite) + 1 if limite > 0 else 1
    total_paginas = math.ceil(total_registros / limite) if limite > 0 else 1 #type: ignore

    # 6. Retorna a página HTML passando os dados E as variáveis de paginação
    return templates.TemplateResponse(
        request=request, 
        name="resultados.html", 
        context={
            "dados": dados_formatados,
            "pagina_atual": pagina_atual,
            "total_paginas": total_paginas,
            "total_registros": total_registros,
            "tem_anterior": offset > 0,
            "tem_proxima": offset + limite < total_registros, # type: ignore
            # Passamos os filtros de volta para o HTML para não perdermos eles ao mudar de página
            "filtros": {
                "uf": uf or "",
                "palavra_chave": palavra_chave or "",
                "valor_minimo": valor_minimo or "",
                "limite": limite
            }
        }
    )