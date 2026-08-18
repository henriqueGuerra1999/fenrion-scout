# Fenrion Scout (nome de trabalho)

Produto de tracking de leilões automóveis europeus para stands: cada stand
define o que anda à procura (marca, modelo, km máximo, preço máximo,
cilindrada, etc) e o Fenrion Scout cruza isso com o que aparece nos sites de
leilão que o stand já consulta manualmente, apresentando os melhores
"matches" de forma clara e apelativa.

Desenhado desde o primeiro dia para servir **vários stands**, não só o que
sugeriu a ideia — é um produto a replicar, não um projeto único.

## Estado atual

- **Esquema de dados** (`schema.sql`): pronto. Multi-cliente, com perfis de
  compra (`wanted_profiles`), catálogo de fontes de leilão
  (`auction_sources`), listagens normalizadas (`auction_listings`) e
  correspondências calculadas (`matches`).
- **Motor de matching** (`matching.py`): pronto e testado (`matches_profile`
  decide se uma listagem bate certo com um perfil; `match_score` dá um grau
  de correspondência 0-100 para ordenar/destacar no dashboard).
- **Serviço FastAPI** (`service.py`): esqueleto pronto, com o mesmo padrão
  de arranque tolerante do `f2car_post_engine` (arranca sem `DATABASE_URL`,
  devolve 503 claro nos endpoints que precisam de BD). Endpoints já
  funcionais: `/clientes`, `/criterios-compra/{client_id}` (o backend do
  formulário de "wanted list"), `/fontes`, `/leiloes/{client_id}`.
- **Adapters de sites de leilão** (`adapters/`): interface pronta
  (`adapters/base.py`), **zero adapters implementados** — é a única peça
  que depende dos sites reais.
- **Apresentação (frontend)**: ainda não iniciada — só faz sentido depois
  de termos dados reais a fluir, para desenhar em cima do que os dados
  realmente permitem mostrar.

## Como as peças encaixam

```
adapter do site X  ─┐
adapter do site Y  ─┼─> auction_listings (normalizado) ─> matching.py ─> matches ─> dashboard/alertas
adapter do site Z  ─┘                                         ^
                                              wanted_profiles ─┘ (o que cada stand procura)
```

Cada adapter só sabe ler UM site e devolver `RawListing` normalizado
(`adapters/base.py`). O resto do sistema nunca sabe de que site veio cada
viatura — por isso adicionar um novo site no futuro é só escrever um
adapter novo, sem tocar em mais nada.

## Próximos passos (por ordem)

1. **Lista dos sites de leilão** que o stand já consulta (a enviar pelo
   Henrique). Para cada site preciso de saber:
   - Precisa de login/conta paga para ver preços e detalhes?
   - Tem alguma política que proíba scraping/acesso automatizado (termos
     de serviço)?
2. Implementar o primeiro adapter (o site mais relevante) e validar o
   fluxo completo ponta a ponta com dados reais.
3. Job periódico (cron) que corre os adapters, grava listagens novas e
   chama `recalcular_matches_para_cliente` para cada stand ativo.
4. Decidir e construir a apresentação: alertas (email/WhatsApp) quando
   surge um match novo, e/ou um dashboard tipo mini-marketplace privado
   por stand (cartões com contagem decrescente até ao fim do leilão,
   badges de qualidade do match, etc) — a desenhar depois do passo 2, com
   dados reais à frente.
5. Provisionar uma base de dados Postgres própria no Render para este
   produto (separada da do F2Car, para os dois produtos terem ciclos de
   vida independentes).

## Notas técnicas

- Mesma stack e convenções do `f2car_post_engine` (FastAPI + Postgres,
  arranque tolerante sem BD, `python3 -m py_compile` antes de cada deploy).
- `DATABASE_URL` é lida de variável de ambiente — ainda não há nenhuma BD
  provisionada para este projeto.
- Testado localmente: compila sem erros, todas as rotas registadas
  corretamente, comportamento 503 gracioso sem BD confirmado, e o motor de
  matching (`matching.py`) validado com um caso de teste manual (ver
  histórico do projeto).
