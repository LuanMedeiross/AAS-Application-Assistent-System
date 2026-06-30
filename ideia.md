# Ideia — Application Assistant

> Visão e contexto do produto. Documento de "por quê". Decisões técnicas ficam em
> `docs/arquitetura.md`; o "o quê" detalhado em `SPEC.md`.

## Problema

Candidatar-se a vagas é um trabalho manual, repetitivo e lento: buscar vagas em várias
plataformas, ler cada descrição, adaptar o currículo, escrever uma carta, preencher o
formulário e enviar. Quem faz isso bem feito gasta 20–40 min por vaga — e por isso acaba
mandando candidaturas genéricas ou aplicando em poucas vagas.

Dois fatos de mercado tornam isso crítico:
- **Velocidade ganha**: candidatar-se nas **primeiras 24h** de uma vaga dá **+64%** de chance
  de entrevista.
- **Personalização ganha**: currículos adaptados ao ATS e à descrição passam mais nos
  filtros automáticos (75% dos CVs são barrados por ATS antes de um humano ver).

Fazer as duas coisas à mão, em escala, é impossível.

## Proposta de valor

Um app que executa o ciclo **descobrir → ranquear → adaptar → preencher → enviar** de ponta a
ponta, com IA (DeepSeek) cuidando do conteúdo e automação de navegador/API cuidando da
execução. O humano fica no comando das decisões importantes (revisar e aprovar), não na
digitação repetitiva.

**Resultado esperado:** candidatar-se a mais vagas, mais rápido, com CV/carta sob medida em
cada uma — sem perder qualidade nem controle.

## Persona

Profissional de **segurança ofensiva/defensiva** (red team, AppSec, security analyst)
buscando vagas na área. Tem perfil técnico, entende de automação e aceita rodar uma
ferramenta local que reutiliza suas sessões logadas. Quer cobertura ampla (BR + tech
internacional) sem abrir mão de candidaturas bem-feitas.

**Cargos-alvo (exemplos):** analista de segurança, red team, AppSec, pentester, security
engineer, security analyst.

## Fluxo do usuário (alto nível)

1. Definir cargos-alvo e revisar o **CV-mestre** (importado do LinkedIn) no dashboard.
2. Logar manualmente uma vez nas plataformas (sessão salva e reutilizada).
3. App descobre vagas em tempo real nas plataformas habilitadas.
4. IA **ranqueia** as vagas por aderência ao perfil.
5. Para as vagas escolhidas, IA **gera CV + carta sob medida** (no idioma da vaga).
6. App **preenche** a candidatura (API ou navegador) e **para antes de enviar**.
7. Usuário **revisa e aprova** no dashboard → app envia e registra.

## Escopo (MVP)

- Plataformas iniciais por prioridade: **Gupy** (API) → InHire (API) → Indeed/Catho
  (navegador) → email direto → LinkedIn (último, anti-bot agressivo).
- CV-mestre importado do **export oficial de dados do LinkedIn** (ZIP/CSVs, sem scraping);
  geração de CV/carta no **idioma da vaga** seguindo `ATS.md`.
- Dashboard local (FastAPI + HTMX) para Profile, vagas ranqueadas, preview e fila de aprovação.
- Aprovação **manual** por padrão (human-in-the-loop).

## Não-escopo (por enquanto)

- Multiusuário / SaaS hospedado (MVP é local, single-user, SQLite).
- Modo 100% automático sem revisão (fica como toggle opcional, depois da fatia vertical).
- Acompanhamento de entrevistas / CRM de candidaturas além do registro básico.
- Plataformas fora da lista priorizada.

## Riscos e ToS (consciência explícita)

- Automação de candidatura **viola os termos** de algumas plataformas; **LinkedIn** é o mais
  agressivo (Cloudflare/reCAPTCHA, risco de bloqueio de conta). Por isso fica por último e
  sempre via sessão manual.
- **Mitigações:** canal API onde existir (Gupy/InHire — sem captcha), sessão logada manual
  (não guardamos senha), human-in-the-loop, circuit breaker para parar ao primeiro sinal de
  bloqueio, e pipeline de captcha (2Captcha) acionado só quando necessário.
- **Uso pretendido:** candidaturas reais do próprio usuário às próprias vagas — não spam em
  massa. Volume e cadência configuráveis para parecer humano.

## Por que vai funcionar

A arquitetura reaproveita um padrão de harness já validado pelo usuário (`automation_launcher`:
browser stealth + plugins por alvo + harness de teste isolado). O risco técnico de automação
está concentrado num núcleo compartilhado e testado; cada plataforma nova é um plugin fino.
