"""
Fenrion Scout -- registo dos adapters ativos.

Cada adapter real (um por site, ex: MobileDeAdapter, AutoScout24Adapter,
OpenLaneAdapter, AutococheAdapter) e adicionado aqui assim que estiver
implementado e testado com uma amostra real do email desse site. O
orquestrador (ingest.py) so conhece esta lista -- nao precisa de saber
quantos ou quais adapters existem.

Vazio por agora -- a preencher um a um assim que tivermos amostras de
email reais de cada site (ver README.md).
"""
from adapters.base import AuctionSourceAdapter

ADAPTERS: list[AuctionSourceAdapter] = [
    # ex: MobileDeAdapter(),
    # ex: AutoScout24Adapter(),
    # ex: OpenLaneAdapter(),
    # ex: AutococheAdapter(),
]
