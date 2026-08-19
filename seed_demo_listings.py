"""
Fenrion Scout -- gera listagens de leilao FABRICADAS para demonstracao.

Uso: enquanto nao ha nenhum adapter real ligado, este script povoa a BD
com viaturas de exemplo (fonte 'demo', claramente identificada como tal),
para poderes mostrar ao stand como e que o resultado final vai aparecer no
painel -- sem depender de nenhuma integracao real ainda estar pronta.

Corre-se manualmente (nao faz parte do servico web):
    DATABASE_URL="postgresql://..." python3 seed_demo_listings.py

Idempotente -- pode correr-se varias vezes sem duplicar dados (usa sempre
os mesmos external_id).

IMPORTANTE: apagar a fonte 'demo' (e as suas listagens, em cascata) antes
de mostrar o produto como estando "ao vivo" com dados reais -- isto e so
para demonstracao do conceito.
"""
import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")

VIATURAS_DEMO = [
    dict(external_id="demo-001", brand="BMW", model="320d", year=2019, km=85000,
         engine_cc=1995, fuel="diesel", gearbox="automatica", condition_grade="sem_danos",
         price_current=14500, listing_url="https://exemplo-leilao.test/demo-001",
         photo_url=None, country="DE", dias_ate_fim=3),
    dict(external_id="demo-002", brand="Volkswagen", model="Golf", year=2018, km=95000,
         engine_cc=1600, fuel="diesel", gearbox="manual", condition_grade="danos_ligeiros",
         price_current=9800, listing_url="https://exemplo-leilao.test/demo-002",
         photo_url=None, country="ES", dias_ate_fim=1),
    dict(external_id="demo-003", brand="Audi", model="A3", year=2020, km=62000,
         engine_cc=1400, fuel="gasolina", gearbox="automatica", condition_grade="sem_danos",
         price_current=17900, listing_url="https://exemplo-leilao.test/demo-003",
         photo_url=None, country="FR", dias_ate_fim=5),
    dict(external_id="demo-004", brand="Mercedes-Benz", model="A 180", year=2017, km=110000,
         engine_cc=1595, fuel="diesel", gearbox="manual", condition_grade="danos_ligeiros",
         price_current=8200, listing_url="https://exemplo-leilao.test/demo-004",
         photo_url=None, country="DE", dias_ate_fim=2),
    dict(external_id="demo-005", brand="Renault", model="Megane", year=2019, km=78000,
         engine_cc=1500, fuel="diesel", gearbox="manual", condition_grade="sem_danos",
         price_current=10500, listing_url="https://exemplo-leilao.test/demo-005",
         photo_url=None, country="ES", dias_ate_fim=4),
]


def seed(database_url: str | None = None) -> int:
    """Insere/atualiza as listagens de demonstracao. Devolve quantas foram
    processadas. Reutilizavel tanto como script standalone (ver main()
    abaixo) como importado a partir de service.py (endpoint /dev/seed-demo-listings)."""
    url = database_url or DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL nao configurada.")

    conn = psycopg2.connect(url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auction_sources (id, name, base_url, country, requires_login, notes)
                VALUES ('demo', 'Fonte de demonstração (dados fabricados)', 'https://exemplo-leilao.test', NULL, false,
                        'NAO E UMA FONTE REAL -- usada so para demonstrar o produto antes das integracoes reais estarem prontas.')
                ON CONFLICT (id) DO NOTHING
                """
            )
            agora = datetime.now(timezone.utc)
            for base in VIATURAS_DEMO:
                v = dict(base)  # copia -- nunca mutar o dict partilhado do modulo
                fim = agora + timedelta(days=v.pop("dias_ate_fim"))
                cur.execute(
                    """
                    INSERT INTO auction_listings (
                        source_id, external_id, brand, model, year, km, engine_cc, fuel,
                        gearbox, condition_grade, price_current, currency, auction_end_at,
                        listing_url, photo_url, country, raw_data, last_seen_at
                    ) VALUES ('demo', %(external_id)s, %(brand)s, %(model)s, %(year)s, %(km)s, %(engine_cc)s,
                              %(fuel)s, %(gearbox)s, %(condition_grade)s, %(price_current)s, 'EUR', %(auction_end_at)s,
                              %(listing_url)s, %(photo_url)s, %(country)s, '{}'::jsonb, now())
                    ON CONFLICT (source_id, external_id) DO UPDATE SET
                        price_current = EXCLUDED.price_current, auction_end_at = EXCLUDED.auction_end_at,
                        last_seen_at = now()
                    """,
                    {**v, "auction_end_at": fim},
                )
        return len(VIATURAS_DEMO)
    finally:
        conn.close()


def main():
    total = seed()
    print(f"Inseridas/atualizadas {total} listagens de demonstração na fonte 'demo'.")


if __name__ == "__main__":
    main()
