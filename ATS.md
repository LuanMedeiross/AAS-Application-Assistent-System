# ATS — Como sobreviver ao Applicant Tracking System

> **Documento crítico.** Todo CV gerado pelo `tailor.py` DEVE seguir estas regras. 75% dos
> currículos são barrados pelo ATS antes de um humano ver. Passar no ATS é pré-requisito para
> qualquer candidatura. Baseado em pesquisa de mercado 2025–2026 (fontes no fim).

## O que é o ATS e como ele decide (2026)

ATS = software que recrutadores usam para filtrar e ranquear candidatos. Em 2026 já não é só
"match de palavra-chave": usa **análise semântica, score de contexto, análise de frequência,
parsing de formato e mapeamento de experiência**. Duas coisas determinam tudo:

1. **Parseabilidade** — o sistema consegue extrair seus dados na ordem certa, sem erro?
2. **Relevância** — seus títulos, skills e bullets batem com a descrição da vaga?

Se o CV não é parseável, o conteúdo nem é avaliado. Se é parseável mas irrelevante, é
ranqueado para baixo. Precisamos das duas.

## Regras de formato (parseabilidade) — OBRIGATÓRIO

- **Layout de coluna única.** Nada de duas colunas, tabelas, caixas de texto, gráficos, ícones,
  barras de skill, fotos. Esses elementos quebram o parser.
- **Fontes web-safe:** Arial, Calibri, Garamond, Georgia ou Times New Roman. Corpo 10–12pt,
  títulos 14–16pt.
- **PDF** como padrão (parsers modernos leem bem; DOCX tem formatação oculta que causa
  inconsistência). Exceção: se a vaga pedir `.doc/.docx` explicitamente, gerar nesse formato.
- **Headings padrão e reconhecíveis**, nesta ordem comprovada:
  1. Contato → 2. Resumo profissional → 3. Skills (técnicas) → 4. Experiência →
  5. Projetos → 6. Educação → 7. Certificações.
- **Sem símbolos custom** em bullets (checkmarks, setas, emojis). Use bullet simples.
- **1–2 páginas.**
- **NUNCA** keyword em texto branco / fonte 1pt / escondida — ATS moderno detecta e o recrutador
  rejeita na hora. (Anti-padrão; o `tailor` jamais deve fazer isso.)

## Regras de conteúdo (relevância)

- **Espelhar o idioma exato da vaga.** Se a descrição diz "stakeholder management" ou
  "resposta a incidentes", use a frase **exata** — o match costuma ser literal. Não troque por
  sinônimo ("comunicação com executivos").
- **Skills matrix no topo.** Recrutador/ATS escaneia ferramentas e tecnologias antes do
  histórico. Liste as skills/ferramentas da vaga que você realmente domina (mesmo que de lab).
- **Bullets com número.** "Configurei SIEM (Wazuh) cobrindo 12 endpoints, reduzindo tempo de
  triagem em 30%" vale muito mais que "trabalhei com SIEM". Meta: métrica em 60–70% dos bullets.
- **Resumo específico**, não genérico. Bom resumo nomeia uma certificação, cita 3 skills
  concretas e um projeto tangível, e declara o cargo-alvo. Ruim: "Buscando posição desafiadora
  em cibersegurança".
- **Acrônimos por extenso + sigla** (ex.: "CompTIA Security+ (Sec+)", "Active Directory (AD)")
  — cobre os dois jeitos que o ATS procura.

## Estratégia para perfil com muito estudo e pouca experiência formal

(Caso do usuário: forte autoestudo em cyber, sem cargo formal ainda.) O CV deve **provar
capacidade com material real e verificável**, posicionado para a vaga:

- **Seção Projetos / Home Lab = seu portfólio prático.** Descreva cada lab como se fosse um
  projeto de trabalho: o que construiu, por quê, o que aprendeu, qual ferramenta/técnica.
  Ex.: "Montei lab de Active Directory (3 VMs) e explorei Kerberoasting, AS-REP roasting e
  movimentação lateral com BloodHound/Impacket."
- **CTFs e plataformas** (HackTheBox, TryHackMe, bug bounty) com horas/resultados concretos.
  Ex.: "200+ horas em TryHackMe; resolvi N máquinas de nível X; write-ups publicados."
- **Certificações** (e em andamento) em seção dedicada perto do topo.
- **Reframe honesto:** autoestudo, projetos e labs são **experiência real demonstrável** — vão
  na seção de experiência/projetos com verbos de ação e métricas. Isso é diferente de inventar
  emprego em empresa que não existiu (não fazemos isso: quebra na entrevista técnica e no
  background check).
- **Keywords da vaga que você domina de verdade** entram naturalmente via projetos e skills.

### O que PODE amplificar vs. o que NÃO pode (linha clara)

**Pode (e deve) amplificar com base na vaga:**
- **Competências e expertise** — destacar ao máximo skills, ferramentas e técnicas que você
  realmente estudou/praticou e que a vaga pede; trazê-las para o topo, com as keywords exatas.
- **Profundidade da descrição** — descrever projetos/labs com mais detalhe técnico e resultado
  quando a vaga valoriza aquilo (ex.: vaga pede SIEM → expandir o que você fez com Wazuh/Splunk no lab).
- **Enquadramento** — posicionar autoestudo/CTFs/projetos como experiência concreta e relevante.

**Não pode fabricar:**
- **Vínculo empregatício** (empresa, cargo, datas) que não existiu.
- **Senioridade/tempo** que não corresponde à realidade (não vira "5 anos de pentest").
- **Certificação** que você não tem.

Regra de ouro: amplificamos **competência demonstrável**, nunca **fatos verificáveis falsos**
(emprego, datas, certificações). O primeiro convence na entrevista; o segundo te queima nela.

## Checklist que o `tailor.py` aplica a cada CV gerado

- [ ] Coluna única, sem tabela/gráfico/ícone, fonte web-safe.
- [ ] Headings padrão na ordem canônica.
- [ ] Idioma do CV = idioma da vaga; keywords-chave da descrição espelhadas **literalmente**.
- [ ] Skills matrix no topo só com o que é real.
- [ ] ≥60% dos bullets com número/resultado.
- [ ] Resumo específico (cert + 3 skills + projeto + cargo-alvo).
- [ ] Acrônimos por extenso + sigla.
- [ ] Projetos/labs descritos como experiência concreta (verbo de ação + ferramenta + resultado).
- [ ] Sem texto escondido / keyword stuffing.
- [ ] 1–2 páginas.

## Como verificar (opcional, futuro)

Rodar o CV gerado por um parser de teste e comparar keywords extraídas vs. descrição da vaga
(score de relevância). Pode virar um passo automático antes da fila de aprovação.

## Fontes
- [ATS Resume Guide 2026 — Best Practices](https://bestjobsearchapps.com/articles/en/ats-resume-guide-2026-format-keywords-and-best-practices-to-beat-applicant-tracking-systems)
- [Jobscan — Anatomy of an ATS-Friendly Resume](https://www.jobscan.co/blog/20-ats-friendly-resume-templates/)
- [ATS Resume Keywords — Ultimate Guide 2026](https://stylingcv.com/blog/ats-resume-keywords-ultimate-guide-2026/)
- [Indeed — How To Write an ATS Resume](https://www.indeed.com/career-advice/resumes-cover-letters/ats-resume-template)
- [Cybersecurity Resume Guide 2026 — Unihackers](https://unihackers.com/blog/cybersecurity-resume-guide)
- [Entry Level Cyber Security Resume Examples — Resume Worded](https://resumeworded.com/entry-level-cyber-security-analyst-resume-example)
- [MyCyberSecurityPath — Resume & Portfolio Guide](https://mycybersecuritypath.com/cybersecurity/resume-portfolio/)
