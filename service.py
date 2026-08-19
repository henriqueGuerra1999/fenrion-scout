"""
Fenrion Scout -- servico de tracking de leiloes automoveis para stands.

Nome de trabalho, muda-se facilmente. Segue o mesmo padrao de arranque
tolerante do f2car_post_engine: se DATABASE_URL nao estiver definida, o
servico continua a arrancar (para nao bloquear deploys/testes), mas os
endpoints que precisam de BD devolvem 503 com uma mensagem clara em vez de
um erro cego.

Multi-cliente desde o primeiro dia -- ao contrario do motor do F2Car, aqui
nao ha um dicionario CLIENTS hardcoded: os stands sao criados via
POST /clientes e guardados na BD, exatamente para este produto ser
replicavel para outros stands sem tocar em codigo.

Estado atual (ver README.md para o plano completo):
  - Esquema de dados: pronto (schema.sql)
  - Formulario de criterios de compra: endpoints prontos abaixo
  - Motor de matching: pronto (matching.py)
  - Adapters de sites de leilao: ainda NENHUM implementado -- a aguardar
    a lista de sites que o stand consulta. Ver adapters/base.py.
  - Job periodico que corre os adapters e recalcula matches: ainda por
    construir (depende de existir pelo menos um adapter real).
"""
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from matching import match_score, matches_profile
from ingest import coletar_todas_as_fontes
from seed_demo_listings import seed as seed_demo_listings

app = FastAPI(title="Fenrion Scout")

DATABASE_URL = os.environ.get("DATABASE_URL")
HERE = os.path.dirname(os.path.abspath(__file__))


def _db_conn():
    if not DATABASE_URL:
        raise HTTPException(
            status_code=503,
            detail="DATABASE_URL nao configurada -- este endpoint precisa de uma base de dados ligada.",
        )
    return psycopg2.connect(DATABASE_URL)


@app.on_event("startup")
def _ensure_schema():
    if not DATABASE_URL:
        print("[startup] DATABASE_URL nao definida -- endpoints de BD ficarao indisponiveis ate ligares uma.")
        return
    try:
        schema_path = os.path.join(HERE, "schema.sql")
        with open(schema_path, encoding="utf-8") as f:
            schema_sql = f.read()
        conn = _db_conn()
        with conn, conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.close()
    except Exception as e:
        print(f"[startup] Nao consegui preparar as tabelas: {e}")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/painel", response_class=FileResponse)
def painel():
    path = os.path.join(HERE, "painel.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="painel.html nao encontrado no servico.")
    return FileResponse(
        path, media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


# ============================================================
# Clientes (stands)
# ============================================================

class ClientPayload(BaseModel):
    id: str
    name: str


@app.post("/clientes")
def criar_cliente(payload: ClientPayload):
    conn = _db_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clients (id, name) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name",
                (payload.id, payload.name),
            )
        return {"ok": True, "client_id": payload.id}
    finally:
        conn.close()


@app.get("/clientes")
def listar_clientes():
    conn = _db_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, name, created_at FROM clients ORDER BY name")
            rows = cur.fetchall()
        return {"clientes": [{"id": r[0], "name": r[1], "criado_em": r[2].isoformat()} for r in rows]}
    finally:
        conn.close()


# ============================================================
# Criterios de compra (a "wanted list" por stand)
# ============================================================
# Um stand pode ter varios perfis ativos em simultaneo (ex: "SUVs ate 15k"
# e "carrinhas comerciais ate 10k"). Isto e o backend do formulario que o
# stand vai preencher.

_PROFILE_COLUMNS = [
    "label", "brand", "model", "year_min", "year_max", "km_max",
    "price_min", "price_max", "engine_cc_min", "engine_cc_max",
    "fuels", "gearbox", "condition_grades", "countries", "active",
]


class WantedProfilePayload(BaseModel):
    label: str
    brand: str | None = None
    model: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    km_max: int | None = None
    price_min: float | None = None
    price_max: float | None = None
    engine_cc_min: int | None = None
    engine_cc_max: int | None = None
    fuels: list[str] = []
    gearbox: str | None = None
    condition_grades: list[str] = []
    countries: list[str] = []
    active: bool = True


def _row_to_profile(row) -> dict:
    keys = ["id", "client_id"] + _PROFILE_COLUMNS + ["created_at", "updated_at"]
    d = dict(zip(keys, row))
    d["created_at"] = d["created_at"].isoformat()
    d["updated_at"] = d["updated_at"].isoformat()
    return d


@app.get("/criterios-compra/{client_id}")
def listar_criterios_compra(client_id: str, apenas_ativos: bool = True):
    conn = _db_conn()
    try:
        query = f"SELECT id, client_id, {', '.join(_PROFILE_COLUMNS)}, created_at, updated_at FROM wanted_profiles WHERE client_id = %s"
        params = [client_id]
        if apenas_ativos:
            query += " AND active"
        query += " ORDER BY created_at DESC"
        with conn, conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return {"client_id": client_id, "perfis": [_row_to_profile(r) for r in rows]}
    finally:
        conn.close()


@app.post("/criterios-compra/{client_id}")
def criar_criterio_compra(client_id: str, payload: WantedProfilePayload):
    conn = _db_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM clients WHERE id = %s", (client_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Cliente '{client_id}' desconhecido. Cria-o primeiro via POST /clientes.")
            cols = ", ".join(_PROFILE_COLUMNS)
            placeholders = ", ".join(["%s"] * len(_PROFILE_COLUMNS))
            values = [getattr(payload, c) for c in _PROFILE_COLUMNS]
            cur.execute(
                f"INSERT INTO wanted_profiles (client_id, {cols}) VALUES (%s, {placeholders}) RETURNING id",
                [client_id] + values,
            )
            new_id = cur.fetchone()[0]
        return {"ok": True, "id": new_id, "client_id": client_id}
    finally:
        conn.close()


@app.delete("/criterios-compra/{client_id}/{profile_id}")
def apagar_criterio_compra(client_id: str, profile_id: int):
    conn = _db_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM wanted_profiles WHERE id = %s AND client_id = %s", (profile_id, client_id))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Perfil nao encontrado para este cliente.")
        return {"ok": True}
    finally:
        conn.close()


# ============================================================
# Fontes de leilao (catalogo -- preenchido quando soubermos os sites reais)
# ============================================================

class AuctionSourcePayload(BaseModel):
    id: str
    name: str
    base_url: str
    country: str | None = None
    requires_login: bool = False
    notes: str | None = None


@app.get("/fontes")
def listar_fontes():
    conn = _db_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, name, base_url, country, requires_login, active, notes FROM auction_sources ORDER BY name")
            rows = cur.fetchall()
        return {
            "fontes": [
                {"id": r[0], "name": r[1], "base_url": r[2], "country": r[3], "requires_login": r[4], "active": r[5], "notes": r[6]}
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.post("/fontes")
def registar_fonte(payload: AuctionSourcePayload):
    conn = _db_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auction_sources (id, name, base_url, country, requires_login, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, base_url = EXCLUDED.base_url,
                    country = EXCLUDED.country, requires_login = EXCLUDED.requires_login, notes = EXCLUDED.notes
                """,
                (payload.id, payload.name, payload.base_url, payload.country, payload.requires_login, payload.notes),
            )
        return {"ok": True, "id": payload.id}
    finally:
        conn.close()


# ============================================================
# Matches -- resultados para o stand consultar
# ============================================================
# Nota: ainda nao ha nenhum job a preencher auction_listings/matches (isso
# depende dos adapters, ver adapters/base.py). Estes endpoints ja ficam
# prontos para quando esse job existir -- e tambem uteis para testar o
# motor de matching manualmente entretanto (ver /leiloes/{client_id}/testar).

@app.get("/leiloes/{client_id}")
def listar_matches(client_id: str, apenas_nao_notificados: bool = False):
    conn = _db_conn()
    try:
        query = """
            SELECT m.id, m.wanted_profile_id, wp.label, l.brand, l.model, l.year, l.km,
                   l.price_current, l.currency, l.auction_end_at, l.listing_url, l.photo_url,
                   l.country, m.score, m.notified, m.created_at
            FROM matches m
            JOIN wanted_profiles wp ON wp.id = m.wanted_profile_id
            JOIN auction_listings l ON l.id = m.listing_id
            WHERE m.client_id = %s
        """
        params = [client_id]
        if apenas_nao_notificados:
            query += " AND NOT m.notified"
        query += " ORDER BY m.created_at DESC"
        with conn, conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return {
            "client_id": client_id,
            "matches": [
                {
                    "id": r[0], "perfil_id": r[1], "perfil_label": r[2],
                    "marca": r[3], "modelo": r[4], "ano": r[5], "km": r[6],
                    "preco": r[7], "moeda": r[8],
                    "fim_leilao": r[9].isoformat() if r[9] else None,
                    "url": r[10], "foto": r[11], "pais": r[12],
                    "score": r[13], "notificado": r[14], "criado_em": r[15].isoformat(),
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


def recalcular_matches_para_cliente(client_id: str):
    """Recorre a todas as listagens de leilao ativas e aos perfis ativos
    deste cliente, e grava um match para cada par que bate certo. Pensado
    para ser chamado depois de cada corrida dos adapters (quando existirem)
    -- por agora pode ser chamado manualmente para testar o motor com dados
    reais assim que houver pelo menos uma fonte com listagens."""
    conn = _db_conn()
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM wanted_profiles WHERE client_id = %s AND active", (client_id,))
            profiles = cur.fetchall()
            cur.execute("SELECT * FROM auction_listings WHERE auction_end_at IS NULL OR auction_end_at > now()")
            listings = cur.fetchall()

            novos = 0
            for profile in profiles:
                for listing in listings:
                    if matches_profile(dict(listing), dict(profile)):
                        score = match_score(dict(listing), dict(profile))
                        cur.execute(
                            """
                            INSERT INTO matches (client_id, wanted_profile_id, listing_id, score)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (wanted_profile_id, listing_id) DO UPDATE SET score = EXCLUDED.score
                            """,
                            (client_id, profile["id"], listing["id"], score),
                        )
                        novos += 1
        return novos
    finally:
        conn.close()


@app.post("/leiloes/{client_id}/recalcular")
def recalcular_matches(client_id: str):
    """Endpoint manual para testar o motor de matching contra o que ja
    estiver em auction_listings, sem esperar por um cron job."""
    total = recalcular_matches_para_cliente(client_id)
    return {"ok": True, "client_id": client_id, "matches_avaliados": total}


# ============================================================
# Ingestao -- corre os adapters de email e atualiza listagens/matches
# ============================================================
# Disparo manual por agora (sem adapters registados ainda, ver
# adapters/registry.py, isto devolve um aviso e nao faz nada). Assim que
# houver pelo menos um adapter real, isto passa a ser chamado por um cron
# job periodico em vez de manualmente.

@app.post("/ingest/coletar")
def ingest_coletar():
    resumo = coletar_todas_as_fontes()
    return resumo


@app.post("/dev/seed-demo-listings")
def dev_seed_demo_listings():
    """TEMPORARIO -- insere viaturas fabricadas (fonte 'demo', claramente
    identificada como tal) para se poder mostrar o produto antes de termos
    qualquer integracao real ligada. Remover este endpoint (e a fonte
    'demo') assim que houver dados reais a fluir."""
    total = seed_demo_listings(DATABASE_URL)
    return {"ok": True, "listagens_processadas": total}
