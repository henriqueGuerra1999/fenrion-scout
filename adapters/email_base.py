"""
Fenrion Scout -- classe base para adapters que leem alertas de pesquisa
guardada por email, em vez de fazer scraping ao site.

Porque esta abordagem em vez de scraping direto:
  - OpenLane so e acessivel com login de concessionario verificado, e os
    termos de utilizacao de plataformas de leilao tipicamente proibem
    acesso automatizado mesmo com sessao valida.
  - AutoScout24 tem protecao anti-bot agressiva (Akamai) e nao tem API de
    leitura publica -- scraping direto seria fragil e arriscado.
  - Mobile.de e a maioria dos marketplaces tambem nao tem API publica
    fiavel.
  - Todos estes sites (incluindo o OpenLane) oferecem "pesquisa guardada"
    com alerta por email -- e essa e a via estavel, dentro das regras de
    cada site, e igual para todos: o cliente configura o alerta uma vez, e
    nos limitamo-nos a ler os emails que o proprio site envia.

Cada site tem o seu proprio formato de email (isso e o unico trabalho
especifico por site) -- implementar EmailListingAdapter.parse_email() para
cada um assim que tivermos uma amostra real do email desse site.
"""
from abc import abstractmethod
from email.message import Message

from adapters.base import AuctionSourceAdapter, RawListing
from email_client import ImapClient, ImapConfig


class EmailListingAdapter(AuctionSourceAdapter):
    """Adapter que le listagens a partir de alertas de pesquisa guardada
    recebidos por email. Subclasses so precisam de definir source_id, name,
    sender_filter, e implementar parse_email()."""

    sender_filter: str  # ex: 'mobile.de', 'noreply@autoscout24.com'

    @abstractmethod
    def parse_email(self, msg: Message) -> list[RawListing]:
        """Le uma unica mensagem de email (ja no formato email.message.Message
        da stdlib) e devolve as listagens normalizadas encontradas nela.
        Um unico email de alerta pode conter varias viaturas -- por isso
        devolve uma lista, nao uma unica RawListing."""
        raise NotImplementedError

    def fetch_listings(self) -> list[RawListing]:
        config = ImapConfig.from_env()
        if not config:
            print(
                f"[{self.source_id}] SCOUT_IMAP_* nao configurado -- "
                "sem acesso a caixa de correio, a saltar esta fonte."
            )
            return []

        listings: list[RawListing] = []
        with ImapClient(config) as client:
            msg_ids = client.search_unseen_from(self.sender_filter)
            for msg_id in msg_ids:
                try:
                    msg = client.fetch_message(msg_id)
                    novas = self.parse_email(msg)
                    listings.extend(novas)
                except Exception as e:
                    # um email mal formado ou um parser desatualizado nao
                    # pode derrubar a corrida toda -- regista e continua.
                    print(f"[{self.source_id}] Erro a processar mensagem {msg_id!r}: {e}")
                finally:
                    # marca como processado mesmo se o parsing falhou, para
                    # nao ficar preso a repetir o mesmo email com erro para
                    # sempre -- o email fica na caixa (nao e apagado) para
                    # se poder investigar manualmente.
                    client.mark_processed(msg_id)

        return listings
