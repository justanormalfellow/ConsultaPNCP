import asyncio
import httpx
import json
from datetime import date, timedelta
from database import db

# ========== CONFIGURAÇÕES ==========
URL_PNCP = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
MODALIDADE = 6
TAMANHO_PAGINA = 50 

# O CAP: Se o script salvar 2000 registros nesta execução, ele para.
# Ajuste para o valor que você achar seguro (ex: 500, 1000, 5000).
LIMITE_MAXIMO_SALVOS = 2000 

PAUSA_ENTRE_PAGINAS = 2.0  # Aumentei para 2 segundos para evitar o 429
PAUSA_ENTRE_JANELAS = 5.0  
# ===================================

async def buscar_pagina(client: httpx.AsyncClient, data_inicial: str, data_final: str, pagina: int) -> dict:
    parametros = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "codigoModalidadeContratacao": MODALIDADE,
        "pagina": pagina,
        "tamanhoPagina": TAMANHO_PAGINA,
    }
    resposta = await client.get(URL_PNCP, params=parametros, timeout=60)
    resposta.raise_for_status()
    return resposta.json()

async def salvar_itens(itens: list) -> int:
    if not itens:
        return 0
    assert db.pool is not None
    async with db.pool.acquire() as conn:
        for item in itens:
            numero_controle = item.get("numeroControlePNCP")
            data_str = item.get("dataPublicacaoPncp", "")[:10]
            data_pub = date.fromisoformat(data_str) if data_str else None
            uf = item.get("unidadeOrgao", {}).get("ufSigla")
            modalidade_nome = item.get("modalidadeNome")

            query = """
                INSERT INTO pncp_contratacoes 
                (numero_controle_pncp, data_publicacao, uf, modalidade_nome, dados_brutos)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (numero_controle_pncp) DO UPDATE SET
                data_publicacao = EXCLUDED.data_publicacao,
                uf = EXCLUDED.uf,
                modalidade_nome = EXCLUDED.modalidade_nome,
                dados_brutos = EXCLUDED.dados_brutos,
                atualizado_em = NOW();
            """
            await conn.execute(query, numero_controle, data_pub, uf, modalidade_nome, json.dumps(item))
    return len(itens)

async def sincronizar_janela(client: httpx.AsyncClient, data_inicial: date, data_final: date, total_atual: int) -> tuple[int, bool]:
    """
    Retorna uma tupla: (quantidade_salva_nesta_janela, deve_parar_tudo)
    """
    str_inicial = data_inicial.strftime("%Y%m%d")
    str_final = data_final.strftime("%Y%m%d")
    print(f"\n📅 Janela: {str_inicial} → {str_final}")

    salvos_janela = 0
    pagina = 1
    total_paginas = 1

    while pagina <= total_paginas:
        dados = await buscar_pagina(client, str_inicial, str_final, pagina)

        if pagina == 1:
            total_paginas = dados.get("totalPaginas", 1)
            print(f"   📊 {dados.get('totalRegistros', 0)} registros em {total_paginas} páginas")

        itens = dados.get("data", [])
        if not itens:
            break

        salvos = await salvar_itens(itens)
        salvos_janela += salvos
        
        total_geral_acumulado = total_atual + salvos_janela
        print(f"   💾 Pág {pagina}/{total_paginas}: {salvos} salvos. (Total geral: {total_geral_acumulado})")

        # 🛑 VERIFICAÇÃO DO CAP
        if total_geral_acumulado >= LIMITE_MAXIMO_SALVOS:
            print(f"\n🛑 CAP DE {LIMITE_MAXIMO_SALVOS} REGISTROS ATINGIDO! Parando o script...")
            return salvos_janela, True # Avisa que deve parar tudo

        pagina += 1
        await asyncio.sleep(PAUSA_ENTRE_PAGINAS)

    return salvos_janela, False

async def sincronizar(data_inicial: date, data_final: date) -> None:
    await db.connect()
    print(f"🔄 Sincronização: {data_inicial} até {data_final} (Cap: {LIMITE_MAXIMO_SALVOS})")

    total_geral = 0
    cursor = data_inicial

    async with httpx.AsyncClient() as client:
        try:
            while cursor <= data_final:
                fim_janela = cursor + timedelta(days=364)
                if fim_janela > data_final:
                    fim_janela = data_final

                # Executa a janela e verifica se deve parar
                salvos, deve_parar = await sincronizar_janela(client, cursor, fim_janela, total_geral)
                total_geral += salvos

                if deve_parar:
                    break # Quebra o loop principal de datas

                cursor = fim_janela + timedelta(days=1)
                if cursor <= data_final:
                    await asyncio.sleep(PAUSA_ENTRE_JANELAS)

            print(f"\n✅ Execução finalizada! Registros salvos nesta rodada: {total_geral}")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                print(f"\n🚫 ERRO 429: O governo bloqueou as requisições (Rate Limit).")
                print(f"Você salvou {total_geral} registros antes do bloqueio. Tente rodar novamente mais tarde.")
            else:
                print(f"❌ Erro na API do PNCP (Status {e.response.status_code}): {e.response.text}")
        except Exception as e:
            print(f"❌ Erro inesperado: {e}")
        finally:
            await db.disconnect()

if __name__ == "__main__":
    HOJE = date.today()
    INICIO = HOJE - timedelta(days=30)
    asyncio.run(sincronizar(INICIO, HOJE))