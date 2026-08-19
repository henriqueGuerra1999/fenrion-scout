"""
Fenrion Scout -- cliente IMAP generico para ler alertas de pesquisa
guardada por email.

Porque IMAP e nao a MCP do Gmail? Este servico corre de forma autonoma no
Render (fora do ambiente do Claude), por isso nao tem acesso as ferramentas
de MCP -- precisa de um mecanismo proprio, portavel, que funcione com
qualquer caixa de correio (Gmail, Outlook, etc) de qualquer cliente futuro,
sem depender de nenhuma integracao especifica da Anthropic. IMAP e o
protocolo universal para isto.

Modelo de acesso: uma unica caixa de correio (ou pasta) recebe os alertas
de TODOS os sites que um cliente usa -- cada adapter filtra pelas mensagens
que lhe interessam pelo remetente (sender_filter). Isto mantem a
configuracao simples: o cliente so precisa de reencaminhar (ou subscrever
diretamente com) os alertas de cada site para uma caixa, e dar-nos acesso a
essa caixa (ou a uma app password, no caso do Gmail/Outlook modernos que já
não aceitam password normal em apps de terceiros).

Configuracao via variaveis de ambiente:
  SCOUT_IMAP_HOST      ex: imap.gmail.com
  SCOUT_IMAP_PORT      default 993 (IMAP sobre SSL)
  SCOUT_IMAP_USER      endereco de email
  SCOUT_IMAP_PASSWORD  password ou app password
  SCOUT_IMAP_FOLDER    pasta a consultar, default 'INBOX'
"""
import email
import imaplib
import os
from dataclasses import dataclass
from email.message import Message


@dataclass
class ImapConfig:
    host: str
    port: int
    user: str
    password: str
    folder: str = "INBOX"

    @classmethod
    def from_env(cls) -> "ImapConfig | None":
        host = os.environ.get("SCOUT_IMAP_HOST")
        user = os.environ.get("SCOUT_IMAP_USER")
        password = os.environ.get("SCOUT_IMAP_PASSWORD")
        if not (host and user and password):
            return None
        return cls(
            host=host,
            port=int(os.environ.get("SCOUT_IMAP_PORT", "993")),
            user=user,
            password=password,
            folder=os.environ.get("SCOUT_IMAP_FOLDER", "INBOX"),
        )


class ImapClient:
    """Wrapper fino sobre imaplib -- so o que os adapters precisam: procurar
    mensagens nao lidas de um remetente, ler o conteudo, e marcar como
    processadas (para nunca reprocessar o mesmo email duas vezes)."""

    def __init__(self, config: ImapConfig):
        self.config = config
        self._conn: imaplib.IMAP4_SSL | None = None

    def __enter__(self):
        self._conn = imaplib.IMAP4_SSL(self.config.host, self.config.port)
        self._conn.login(self.config.user, self.config.password)
        self._conn.select(self.config.folder)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn.logout()

    def search_unseen_from(self, sender_filter: str) -> list[bytes]:
        """Devolve os IDs (bytes) das mensagens nao lidas cujo remetente
        contem sender_filter (ex: 'alerts@mobile.de' ou so 'mobile.de')."""
        typ, data = self._conn.search(None, f'(UNSEEN FROM "{sender_filter}")')
        if typ != "OK":
            return []
        return data[0].split()

    def fetch_message(self, msg_id: bytes) -> Message:
        typ, data = self._conn.fetch(msg_id, "(RFC822)")
        if typ != "OK":
            raise RuntimeError(f"Nao consegui ler a mensagem {msg_id!r} (IMAP fetch falhou).")
        raw = data[0][1]
        return email.message_from_bytes(raw)

    def mark_processed(self, msg_id: bytes):
        """Marca como lida, para nao ser apanhada outra vez na proxima
        corrida. Deliberadamente nao apaga nem move -- mantem o email como
        registo/auditoria caso seja preciso depurar um parser no futuro."""
        self._conn.store(msg_id, "+FLAGS", "\\Seen")


def extract_text_and_html(msg: Message) -> tuple[str, str]:
    """Devolve (corpo_texto, corpo_html) de uma mensagem de email, tratando
    tanto mensagens simples como multipart. A maioria dos alertas destes
    sites vem em HTML -- os parsers de cada adapter vao trabalhar
    principalmente sobre o corpo_html."""
    texto, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if part.get_content_disposition() == "attachment":
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if content_type == "text/plain" and not texto:
                texto = decoded
            elif content_type == "text/html" and not html:
                html = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace") if payload else ""
        except Exception:
            decoded = ""
        if msg.get_content_type() == "text/html":
            html = decoded
        else:
            texto = decoded
    return texto, html
