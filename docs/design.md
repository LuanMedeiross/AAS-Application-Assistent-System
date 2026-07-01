# Design — Application Assistant

> Design do dashboard e das prompts da IA. UI server-rendered (FastAPI + Jinja2 + HTMX),
> sem build de JS. Sem emojis/símbolos na UI sem pedido — estado se comunica por cor/layout.

## Telas

### 1. Dashboard (`/`)
Resumo geral e ponto de partida.
```
┌──────────────────────────────────────────────────────────────┐
│ Application Assistant                         [Profile] [Audit]│
├──────────────────────────────────────────────────────────────┤
│  Sessões:  Gupy [ok]   Indeed [expirada]   LinkedIn [—]       │
│                                                                │
│  Cargos-alvo: red team, appsec, security analyst   [Buscar]   │
│                                                                │
│  Fila de aprovação (3)                                         │
│   • Pentester — Acme            score 88   [Revisar]           │
│   • AppSec Eng — Beta           score 81   [Revisar]           │
│   • Security Analyst — Gamma    score 74   [Revisar]           │
│                                                                │
│  Últimas candidaturas: 12 enviadas · 2 erros                  │
└──────────────────────────────────────────────────────────────┘
```

### 2. Profile (`/profile`)
Editar dados + importar do LinkedIn.
```
┌──────────────────────────────────────────────────────────────┐
│ Profile                                  [Importar do LinkedIn]│
├──────────────────────────────────────────────────────────────┤
│ Nome [____]  Email [____]  Telefone [____]  Local [____]      │
│ Resumo profissional [__________________________________]      │
│ Experiências  [+ adicionar]                                   │
│   - Cargo / Empresa / período / descrição                     │
│ Skills [tag tag tag +]                                        │
│ Cargos-alvo (keywords) [tag tag +]                            │
│ Idiomas [pt, en]                                              │
│                                            [Salvar]           │
└──────────────────────────────────────────────────────────────┘
```
"Importar do LinkedIn" abre/usa a sessão manual, extrai dados e pré-preenche os campos para o
usuário revisar (não salva automático sem revisão).

### 3. Vagas ranqueadas (`/jobs`)
Lista ordenada por score, com filtros.
```
┌──────────────────────────────────────────────────────────────┐
│ Vagas    [plataforma ▾] [status ▾] [score min __]             │
├──────────────────────────────────────────────────────────────┤
│ 88  Pentester — Acme         Gupy    [Gerar CV] [Preparar]    │
│ 81  AppSec Eng — Beta        InHire  [Gerar CV] [Preparar]    │
│ 74  Security Analyst — Gamma Indeed  tailored   [Preparar]    │
│ 60  SOC Analyst — Delta      Catho   ranked     [Gerar CV]    │
└──────────────────────────────────────────────────────────────┘
```
Cada linha expande (HTMX) mostrando descrição, justificativa do score e requisitos ausentes.

### 4. Preview CV/carta (`/jobs/{id}/preview`)
Mostra o PDF gerado + carta, lado a lado com a descrição da vaga, antes de preparar.

### 5. Revisar candidatura (fila de aprovação)
```
┌──────────────────────────────────────────────────────────────┐
│ Revisar: Pentester — Acme (Gupy)                              │
├──────────────────────────────────────────────────────────────┤
│ [PDF do CV]        Respostas do formulário:                   │
│ [carta]             - Pretensão salarial: [____] (a revisar)  │
│                     - Disponibilidade: imediata               │
│                     - Pergunta X: <resposta IA>               │
│ Campos não resolvidos pela IA: 1   (destaque)                 │
│                          [Editar] [Aprovar e enviar] [Rejeitar]│
└──────────────────────────────────────────────────────────────┘
```

## Fluxo de navegação (HTMX)

- Ações (`Buscar`, `Gerar CV`, `Preparar`, `Aprovar`) são POSTs HTMX que **trocam fragmentos**
  (a linha da vaga, o card da fila) sem recarregar a página.
- Operações longas (discover/tailor) mostram estado `processando` no próprio fragmento e
  atualizam quando terminam (polling HTMX ou resposta direta).
- Estado por **cor/tipografia**: `ok`/`enviada` (neutro-positivo), `expirada`/`erro` (destaque),
  `processando` (esmaecido). Sem ícones decorativos.

## Design das prompts da IA

Princípios: instrução curta, **saída JSON estrita**, contexto mínimo necessário, idioma
controlado. Sempre validar contra `schemas.py`.

### Ranker (`deepseek-reasoner`)
- **Entrada:** `target_roles` + `seniority` + resumo do Profile (skills/experiência) +
  título/descrição da vaga.
- **Tarefa:** pontuar 0–100 a aderência, justificar em 1–2 frases, listar requisitos ausentes.
  **Penalizar descompasso de senioridade** (ex.: vaga sênior para perfil entry).
- **Saída:** `{ score, reason, missing[] }`. Sem texto fora do JSON.

### Tailor (`deepseek-chat`)
- **Entrada:** `Profile.master_cv` + descrição da vaga + regras do `ATS.md` + `HUMANIZE.md`.
- **Voz humana (HUMANIZE.md):** ritmo variado (frases curtas + longas), detalhe específico real
  por parágrafo, micro-episódio na carta, zero vocabulário/clichê de IA, carta de 200–300 palavras.
- **Tarefa:** (1) detectar idioma da vaga; (2) gerar CV **no formato ATS** (ver `ATS.md`),
  adaptado agressivamente à descrição — keywords espelhadas literalmente, skills matrix, bullets
  com métrica; (3) escrever carta curta no mesmo idioma.
- **Amplificar competências (não fabricar fatos):** destaca ao máximo skills/expertise reais que
  a vaga pede e enfatiza autoestudo/projetos/home labs como experiência concreta; **não fabrica
  vínculo empregatício, senioridade nem certificação** (ver `ATS.md` — "Pode vs. Não pode").
  Lacuna de experiência → seção Projetos/Labs forte.
- **Saída:** `{ language, cv{...}, cover_letter }`. Validar contra `schemas.py` + checklist do `ATS.md`.

### Form agent (`deepseek-chat`, canal browser)
- **Entrada:** `FormField[]` (label/tipo/opções) + Profile + dados da candidatura.
- **Tarefa:** mapear cada campo para um valor; marcar como `unknown` o que não souber responder
  com segurança (em vez de chutar).
- **Saída:** `{ fields[], unknown[] }`. Campos `unknown` são destacados para o usuário no review.

## Convenção de erros na UI
- Falha de sessão → banner "sessão expirada, rode `login.py <plataforma>`".
- Circuit breaker disparado → plugin marcado como `pausado` com motivo.
- Campo `unknown` do form agent → bloqueia "Aprovar e enviar" até o usuário preencher.
