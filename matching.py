"""
Fenrion Scout -- motor de matching.

Compara uma listagem normalizada de leilao (RawListing, ou a linha
equivalente vinda da BD) contra um perfil de critérios de compra do stand
(wanted_profiles) e decide se e um match, com um grau de correspondencia
(score 0-100) para o stand perceber a qualidade do match de relance.

Logica deliberadamente simples e legivel (mesmo estilo do passes_filters do
motor do F2Car) -- cada campo do perfil so filtra se estiver preenchido;
campos vazios/null no perfil = "aceita qualquer valor".
"""


def _texto_bate(valor: str | None, alvo: str | None) -> bool:
    """Comparacao tolerante para marca/modelo -- case-insensitive e por
    substring, para "Golf" bater certo com "VW Golf GTI" por exemplo."""
    if not alvo:
        return True
    if not valor:
        return False
    return alvo.strip().lower() in valor.strip().lower()


def matches_profile(listing: dict, profile: dict) -> bool:
    """listing e profile sao dicts com as chaves do esquema (ver
    schema.sql) -- funciona tanto com uma RawListing.__dict__ como com uma
    linha lida da BD ja convertida em dict."""

    if not _texto_bate(listing.get("brand"), profile.get("brand")):
        return False
    if not _texto_bate(listing.get("model"), profile.get("model")):
        return False

    year = listing.get("year")
    if profile.get("year_min") and (year is None or year < profile["year_min"]):
        return False
    if profile.get("year_max") and (year is None or year > profile["year_max"]):
        return False

    km = listing.get("km")
    if profile.get("km_max") and (km is None or km > profile["km_max"]):
        return False

    price = listing.get("price_current")
    if profile.get("price_min") and (price is None or price < profile["price_min"]):
        return False
    if profile.get("price_max") and (price is None or price > profile["price_max"]):
        return False

    cc = listing.get("engine_cc")
    if profile.get("engine_cc_min") and (cc is None or cc < profile["engine_cc_min"]):
        return False
    if profile.get("engine_cc_max") and (cc is None or cc > profile["engine_cc_max"]):
        return False

    fuels = profile.get("fuels") or []
    if fuels and listing.get("fuel") not in fuels:
        return False

    if profile.get("gearbox") and listing.get("gearbox") != profile["gearbox"]:
        return False

    grades = profile.get("condition_grades") or []
    if grades and listing.get("condition_grade") not in grades:
        return False

    countries = profile.get("countries") or []
    if countries and listing.get("country") not in countries:
        return False

    return True


def match_score(listing: dict, profile: dict) -> int:
    """Grau de correspondencia 0-100, so calculado para listagens que ja
    passaram matches_profile(). Nao e uma ciencia exata -- e uma heuristica
    para ordenar/destacar os melhores matches no dashboard (ex: "match
    perfeito" vs "match parcial"). Cada criterio preenchido no perfil e
    testado e conta pontos proporcionalmente ao numero de criterios ativos
    -- assim um perfil com poucos criterios preenchidos e mais facil de
    pontuar 100%, e um perfil muito especifico so pontua alto se bater
    certo em tudo."""

    criterios = []

    if profile.get("brand"):
        criterios.append(_texto_bate(listing.get("brand"), profile.get("brand")))
    if profile.get("model"):
        criterios.append(_texto_bate(listing.get("model"), profile.get("model")))
    if profile.get("year_min") or profile.get("year_max"):
        year = listing.get("year")
        dentro = year is not None
        if dentro and profile.get("year_min"):
            dentro = year >= profile["year_min"]
        if dentro and profile.get("year_max"):
            dentro = year <= profile["year_max"]
        criterios.append(dentro)
    if profile.get("km_max"):
        km = listing.get("km")
        criterios.append(km is not None and km <= profile["km_max"])
    if profile.get("price_max"):
        price = listing.get("price_current")
        # margem: preco bem abaixo do limite pontua melhor que rente ao limite
        # (cast a float -- o Postgres devolve NUMERIC como Decimal, que nao
        # se pode multiplicar diretamente por um float)
        if price is None:
            criterios.append(False)
        else:
            price = float(price)
            price_max = float(profile["price_max"])
            criterios.append(price <= price_max * 0.85 or price <= price_max)
    if profile.get("fuels"):
        criterios.append(listing.get("fuel") in profile["fuels"])
    if profile.get("condition_grades"):
        criterios.append(listing.get("condition_grade") in profile["condition_grades"])

    if not criterios:
        return 100  # perfil sem criterios preenchidos -- qualquer coisa e "match total"

    return round(100 * sum(1 for c in criterios if c) / len(criterios))
