"""
Fenrion Scout -- interface comum para adapters de sites de leilao.

Cada site de leilao (Copart, BCA, IAAI-Europe, leiloes de seguradoras, etc)
tem o seu proprio formato de pagina/API. Um "adapter" e um modulo pequeno
que sabe ler UM site especifico e devolver a lista de viaturas em formato
normalizado (RawListing) -- o resto do sistema (matching, base de dados,
apresentacao) nunca precisa de saber de que site veio cada viatura.

Para adicionar um novo site de leilao no futuro:
  1. Criar um ficheiro novo em adapters/ (ex: adapters/copart_eu.py)
  2. Implementar uma classe que herda de AuctionSourceAdapter
  3. Implementar fetch_listings() devolvendo uma lista de RawListing
  4. Registar o adapter em adapters/registry.py (ainda por criar quando
     soubermos os sites reais)

Nao ha nenhuma logica especifica de nenhum site aqui -- fica tudo pronto a
plugar assim que o Henrique enviar a lista de leiloes que o stand consulta.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawListing:
    """Uma viatura em leilao, ja normalizada para o esquema comum do
    Fenrion Scout (ver schema.sql / auction_listings)."""

    external_id: str            # id do leilao no site de origem -- usado para dedupe
    listing_url: str
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    km: int | None = None
    engine_cc: int | None = None        # cilindrada
    fuel: str | None = None             # 'gasolina' | 'diesel' | 'hibrido' | 'eletrico' | 'gpl'
    gearbox: str | None = None          # 'manual' | 'automatica'
    condition_grade: str | None = None  # ex: 'sem_danos' | 'danos_ligeiros' | 'sinistrado'
    price_current: float | None = None  # lance atual ou preco de reserva, consoante o site
    currency: str = "EUR"
    auction_end_at: datetime | None = None
    photo_url: str | None = None
    country: str | None = None          # pais onde o leilao decorre
    raw: dict = field(default_factory=dict)  # payload original -- nunca perder informacao


class AuctionSourceAdapter(ABC):
    """Cada site de leilao suportado implementa esta interface."""

    source_id: str   # slug estavel, tem de bater certo com auction_sources.id na BD
    name: str         # nome legivel, ex: "Copart Europe"
    requires_login: bool = False

    @abstractmethod
    def fetch_listings(self) -> list[RawListing]:
        """Vai buscar o estado atual dos leiloes ativos neste site e
        devolve-os ja normalizados. Deve ser idempotente e seguro de
        chamar repetidamente (ex: de um cron) -- a insercao na BD trata da
        deduplicacao via (source_id, external_id)."""
        raise NotImplementedError
