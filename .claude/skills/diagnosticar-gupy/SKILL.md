---
name: diagnosticar-gupy
description: >-
  Metodologia para diagnosticar e consertar falhas no fluxo de candidatura automática da Gupy
  (app/platforms/gupy/apply.py + core/form_extract + form_fill + ai/form_agent). Use SEMPRE que
  uma candidatura ficar em needs_review, incomplete, error, ou for FALSO POSITIVO (reportada como
  enviada sem finalizar). Codifica as técnicas de scraping, o catálogo de causas conhecidas
  (A–G + finalize), os snippets de dump de DOM, as regras de segurança (idempotência) e as
  armadilhas já resolvidas — para não reaprender nem regredir. Validada: levou 19 candidaturas de
  ~13 falso-positivos para 18 confirmadas pela Gupy, corrigindo 7 causas.
---

# Diagnosticar o fluxo de candidatura da Gupy

> Complementa `app/platforms/gupy/GUPY.md` (mecânica) com o **método de diagnóstico**. Quando uma
> vaga não finaliza direito, siga isto em vez de tentar adivinhar.

## Quando usar
- Candidatura ficou em `needs_review` / `incomplete` / `error`.
- **Falso positivo**: reportada "sent" mas o painel da Gupy mostra iniciada e **não finalizada**.
- Comportamento diferente entre lote (headless/concorrente) e execução única (headed).

## Regras de segurança (LER ANTES)
1. **Gupy é IDEMPOTENTE**: re-candidatar-se retoma a **MESMA `application id`** (verificado — o id
   na URL `/applications/<id>/` não muda). Logo **re-rodar o apply NÃO duplica** a candidatura →
   diagnosticar/reconciliar direto na vaga real é seguro.
2. **A Gupy NÃO marca "já candidatado" no link público**: a `jobUrl` de uma vaga já enviada ainda
   mostra "Candidatar-se" e `_detect_step` retorna `start`. Não confie nisso para "já aplicado".
3. **NUNCA reportar `sent` sem confirmação**: só após a tela `"Candidatura finalizada!"` /
   "Acompanhar candidatura" (`_finalized_ok`). Falso positivo = FALHA em produção.
4. **Teste DIRETO na vaga com problema** (o estado da Gupy fica "sujo" — campos auto-salvos e
   desabilitados). Reproduzir noutra vaga esconde o bug.

## Método (5 passos)
1. **Reproduza o fluxo na própria vaga**, headless, capturando o log:
   navegue via os helpers do plugin (`ga._detect_step`, `ga._advance`, `ga._APPLY_LINK`,
   `ga._COMPANY_SCOPE`) até o passo que falha; passe um `log_fn=lista.append` para o
   `run_auto_apply` OU replique o loop e imprima cada etapa (`[i] etapa: {kind}`).
2. **Dumpe o estado do DOM no passo que falha** (é aqui que o bug aparece). Para cada campo:
   `disabled`, `readonly`, `value`, `checked`, `aria-required`. Para botões: `text`, `disabled`,
   `data-testid`. E: `[role=dialog]`/modais e `.error-message`/`[role=alert]`. Snippets abaixo.
3. **Compare o que o agente respondeu vs o que falhou**: rode `to_questions` + `form_agent.map_form`
   + `apply_answers` e imprima `plan.answers`, `plan.unknown` e o `failed` retornado.
4. **Case com o catálogo de causas** (abaixo) e ache a CAMADA certa do fix
   (extract / fill / agent / apply).
5. **Corrija, re-teste na MESMA vaga** (deve dar `failed=[]` / `unknown=[]`), depois reconcilie
   (`scripts/reconcile_applied.py --threads N`).

## Catálogo de causas conhecidas
| Cód | Sintoma | Causa | Camada / Fix |
|---|---|---|---|
| **A** | `.fill()` trava 30s; `<textarea disabled>valor</textarea>` | Gupy auto-salva e **desabilita** campo respondido; no re-run tentamos reescrever | `core/form_fill.apply_answers`: se `is_editable()` falso → já respondido (OK se tem valor); `fill(timeout=10000)` |
| **B** | uma opção vira `unknown`; nomes `checkbox-XXXX-0/1/2` | checkbox de opção única com **nomes indexados** → cada um virava uma pergunta | `core/form_extract.to_questions`: agrupa por nome-base `re.sub(r'-\d+$','',name)`; `form_fill` clica por prefixo `name^="base-"` |
| **C** | campo preenchido com `"unknown"`/"não sei"; ou RG/CPF | modelo escreveu resposta-lixo para dado pessoal que não temos | `ai/form_agent._sanitize`: `_NON_ANSWERS` → vira `unknown` (não escreve). Prompt: dado pessoal ausente → `unknown`, nunca escrever "unknown" |
| **D** | 40+ perguntas, mesma pergunta repetida ~30x | form gigante de recrutamento interno (Vivo) com grupo radio/checkbox "explodido" | mesmo fix B; e faltam dados pessoais (RG) → ver EXTRAS/Preferências |
| **E** | loop `etapa: advance` (heading "Dados adicionais"); radio não pré-selecionado | empresa só tem `radioGroupIsCompanyEmployeeTitle` (sem a de indicação) → `_detect_step` não via "dados" e o save não avança sem o radio respondido no React | `gupy/apply.py`: `_DADOS_RADIOS` (detecta por qualquer um dos dois radios) + **`.click(force=True)` do Playwright** na label do "Não" (clique via JS NÃO dispara o onChange do React, mesmo com o radio HTML-checked) |
| **F** | `failed` num campo VAZIO e habilitado; `name` contém `"`/aspas | seletor `[name="...\"...\""]` quebra com aspas embutidas → `_locate_text` não acha | `core/form_fill._locate_text`: escapar `"`/`\`; fallback por ÍNDICE via JS (`findIndex` + `.nth(idx)`) |
| **G** | após o save da dados o step NÃO muda; sem erro/campo-vazio; `saveDisabled=false` | empresa **SEM formulário de perguntas** → o save abre DIRETO o **modal "Personalizar candidatura"**, que sobrepõe o form da dados no DOM → `_detect_step` via "dados" de novo | `gupy/apply.py`: modal é ETAPA própria — `_PERSONALIZE_MODAL='#dialog-save-personalization-step'` → `kind='modal'` → clicar "Personalizar" (cobre com/sem perguntas da empresa) |
| **Finalize** | reportou `sent` mas não finalizou | fechávamos o navegador antes do submit completar (headless/carga) | `gupy/apply.py._finalized_ok`: espera "Candidatura finalizada!" antes de `sent`; senão `error` |

## Snippets de dump (reutilize)
Estado dos campos no escopo das perguntas da empresa (`.curriculum-content`):
```js
() => { const norm=s=>(s||'').replace(/\s+/g,' ').trim();
  const scope=document.querySelector('.curriculum-content')||document;
  return [...scope.querySelectorAll('input,textarea,select')].map(el=>({
    tag:el.tagName.toLowerCase(), type:el.getAttribute('type')||'',
    name:(el.getAttribute('name')||'').slice(0,55), disabled:!!el.disabled, readonly:!!el.readOnly,
    value:norm((el.value??'').toString()).slice(0,30), ariaReq:el.getAttribute('aria-required'),
    checked:el.checked })); }
```
Botões + modais + erros (qualquer tela, ex.: finalize):
```js
() => { const norm=s=>(s||'').replace(/\s+/g,' ').trim();
  const vis=el=>{const r=el.getBoundingClientRect();const s=getComputedStyle(el);return s.display!=='none'&&s.visibility!=='hidden'&&(r.width+r.height)>0;};
  return { url:location.href, heading:norm((document.querySelector('main h1,main h2')||{}).innerText||''),
    buttons:[...document.querySelectorAll('button,[role=button],a[data-testid]')].filter(vis).map(b=>({text:norm(b.innerText).slice(0,45),disabled:!!b.disabled,testid:b.getAttribute('data-testid')||''})),
    dialogs:[...document.querySelectorAll('[role=dialog],[class*=modal i],[class*=Dialog]')].filter(vis).map(d=>norm(d.innerText).slice(0,240)),
    errors:[...document.querySelectorAll('.error-message,[role=alert]')].map(e=>norm(e.innerText)).filter(t=>t.length>1&&t.length<160) }; }
```

## Esqueleto de script de diagnóstico
```python
from app.core.browser import BrowserHarness
from app.platforms.gupy import apply as ga
from app.core.form_extract import EXTRACT_JS, to_questions
from app.core.form_fill import apply_answers
from app.ai import form_agent
# ... carregar job/app_row/profile ...
with BrowserHarness(headless=True) as h:
    ctx=h.new_context('gupy'); page=ctx.new_page(); page.goto(job.url); ga._settle(page)
    for i in range(14):
        kind=ga._detect_step(page)
        if kind in ('company','personalize','modal','done'): break   # pare no passo que quer inspecionar
        if kind=='start': ga._advance(page,[('sel',ga._APPLY_LINK)])
        elif kind=='dados': ga._advance(page,[('sel','button[name=\"saveAndContinueButton\"]'),('text','Salvar e continuar')])
        elif kind=='respond_now': ga._advance(page,[('aria','Responder agora'),('text','Responder agora')])
        else:
            if not ga._advance(page,[('text','Continuar'),('text','Salvar e continuar')]): print('travou',kind); break
    print(page.evaluate(STATE_JS))                     # <- estado dos campos
    qs=to_questions(page.evaluate(EXTRACT_JS, ga._COMPANY_SCOPE))
    plan=form_agent.map_form(qs, profile=cv, cover_letter=cover, job=job_d, extras=extras)
    print('failed=', apply_answers(page, qs, plan.answers), 'unknown=', plan.unknown)
    ctx.close()
```

## Acertos & armadilhas (memória de guerra)
- ✖➜✔ **Erro de diagnóstico que quase virou "não tem conserto":** na Causa G eu declarei a vaga
  "career page quebrada" porque o save não avançava e não havia erro/campo-vazio. **Estava errado** —
  era um MODAL que eu não tinha dumpado. **Lição de ouro: sempre inclua `[role=dialog]`/modais no
  dump ANTES de concluir "página anômala".** Se o step não muda mas não há erro nem campo vazio,
  é modal (ou overlay), não defeito.
- ✔ **Headed vs headless** foi a chave do falso positivo: headed finalizava, headless não → o
  problema era não esperar a confirmação, não o código de navegação.
- ✔ Confirmar **idempotência** (mesma application id) ANTES de reconciliar em massa evitou pânico
  de duplo envio.
- ✖ Não confie em `applicationDeadline`/badges pra status (ver GUPY.md). Nem em "já candidatado"
  na jobUrl.
- ✖ `.fill()` default = 30s: num campo disabled trava o fluxo inteiro. Sempre timeout curto.
- ✖ Re-rodar diagnóstico numa vaga já tocada mostra estado sujo (campos disabled) — interprete
  como sinal, não como bug novo.
- ✔ Rode em `--dry-run`/dump antes de qualquer clique irreversível ("Salvar e continuar" das
  perguntas da empresa e "Finalizar" travam/enviam).
