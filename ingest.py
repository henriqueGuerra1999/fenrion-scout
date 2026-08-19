"""
Fenrion Scout -- orquestrador de ingestao.

Corre todos os adapters registados (adapters/registry.py), grava as
listagens novas/atualizadas em auction_listings, e recalcula os matches
para todos os clientes com perfis ativos.

Pensado para ser chamado periodicamente (cron) assim que houver pelo menos
um adapter real -- ver /ingest/coletar em service.py para o disparo manual
usado em testes e enquanto nao ha cron configurado.
"""
import os

import psycopg2
import psycopg2.extras

from adapters.registry import ADAPTERS
from matching import match_score, matches_profile

DATABASE_URL = os.environ.get("DATABASE_URL")


def _db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL nao configurada.")
    return psycopg2.connect(DATABASE_URL)


def _upsert_listing(cur, source_id: str, listing) -> int:
    cur.execute(
        """
        INSERT INTO auction_listings (
            source_id, external_id, brand, model, year, km, engine_cc, fuel,
            gearbox, condition_grade, price_current, currency, auction_end_at,
            listing_url, photo_url, country, raw_data, last_seen_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (source_id, external_id) DO UPDATE SET
            brand = EXCLUDED.brand, model = EXCLUDED.model, year = EXCLUDED.year,
            km = EXCLUDED.km, engine_cc = EXCLUDED.engine_cc, fuel = EXCLUDED.fuel,
            gearbox = EXCLUDED.gearbox, condition_grade = EXCLUDED.condition_grade,
            price_current = EXCLUDED.price_current, currency = EXCLUDED.currency,
            auction_end_at = EXCLUDED.auction_end_at, listing_url = EXCLUDED.listing_url,
            photo_url = EXCLUDED.photo_url, country = EXCLUDED.country,
            raw_data = EXCLUDED.raw_data, last_seen_at = now()
        RETURNING id
        """,
        (
            source_id, listing.external_id, listing.brand, listing.model, listing.year,
            listing.km, listing.engine_cc, listing.fuel, listing.gearbox,
            listing.condition_grade, listing.price_current, listing.currency,
            listing.auction_end_at, listing.listing_url, listing.photo_url,
            listing.country, psycopg2.extras.Json(listing.raw or {}),
        ),
    )
    return cur.fetchone()[0]


def coletar_todas_as_fontes() -> dict:
    """Corre cada adapter registado, grava as listagens na BD, e recalcula
    matches para todos os clientes com perfis ativos. Devolve um resumo
    para logging/depuracao."""
    resumo = {"fontes_corridas": 0, "listagens_gravadas": 0, "erros": [], "matches_recalculados": 0}

    if not ADAPTERS:
        resumo["aviso"] = "Nenhum adapter registado ainda (ver adapters/registry.py)."
        return resumo

    conn = _db_conn()
    try:
        with conn, conn.cursor() as cur:
            for adapter in ADAPTERS:
                resumo["fontes_corridas"] += 1
                try:
                    listings = adapter.fetch_listings()
                    for listing in listings:
                        _upsert_listing(cur, adapter.source_id, listing)
                        resumo["listagens_gravadas"] += 1
                except Exception as e:
                    resumo["erros"].append(f"{adapter.source_id}: {e}")

        # recalcula matches para todos os clientes com pelo menos um perfil ativo
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT DISTINCT client_id FROM wanted_profiles WHERE active")
            client_ids = [r["client_id"] for r in cur.fetchall()]

            for client_id in client_ids:
                cur.execute("SELECT * FROM wanted_profiles WHERE client_id = %s AND active", (client_id,))
                profiles = cur.fetchall()
                cur.execute("SELECT * FROM auction_listings WHERE auction_end_at IS NULL OR auction_end_at > now()")
                listings_rows = cur.fetchall()

                for profile in profiles:
                    for listing_row in listings_rows:
                        if matches_profile(dict(listing_row), dict(profile)):
                            score = match_score(dict(listing_row), dict(profile))
                            cur.execute(
                                """
                                INSERT INTO matches (client_id, wanted_profile_id, listing_id, score)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (wanted_profile_id, listing_id) DO UPDATE SET score = EXCLUDED.score
                                """,
                                (client_id, profile["id"], listing_row["id"], score),
                            )
                            resumo["matches_recalculados"] += 1
    finally:
        conn.close()

    return resumo


if __name__ == "__main__":
    resultado = coletar_todas_as_fontes()
    print(resultado)
