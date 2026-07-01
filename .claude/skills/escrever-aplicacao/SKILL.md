---
name: escrever-aplicacao
description: Use SEMPRE que for escrever ou revisar qualquer texto de candidatura a vaga — carta de apresentação, resumo/summary de CV, bullets de experiência, ou respostas de formulário de aplicação. Garante voz humana (não detectável como IA) + formato ATS. Gatilhos - "escreva a carta", "gere o CV", "adapte o currículo", "responda o formulário da vaga", "texto de candidatura", "cover letter".
---

# Escrever uma aplicação (voz humana + ATS)

Toda vez que eu produzir texto que vai para um recrutador, sigo este processo. Objetivo duplo:
**passar no ATS** (robô lê/ranqueia) e **não soar como IA** (humano não desconfia). As regras
completas vivem em `ATS.md` e `HUMANIZE.md` na raiz do projeto — leia-os quando precisar do
detalhe; o essencial está aqui.

## Princípios inegociáveis

1. **Especificidade real é o melhor disfarce.** Cada afirmação genérica vira cena + número, com
   ferramenta/alvo/resultado que a pessoa realmente viveu (base: `curriculum/master_cv.json`).
2. **Amplificar competência, nunca fabricar fato.** Pode destacar/aprofundar skills reais; não
   inventa vínculo empregatício, senioridade ou certificação (ver `ATS.md`).
3. **Idioma = idioma da vaga.** Detecte e escreva no mesmo idioma da descrição.

## Antes de escrever
- Leia a descrição da vaga; extraia as keywords exatas (para espelhar — ATS).
- Puxe do `master_cv` os fatos reais mais aderentes (projetos, bug bounty, labs, métricas).
- Defina o idioma pela descrição.

## Ao escrever
- **Varie o ritmo:** misture frases curtas (5–8 palavras) e longas (25–35). Nunca uniforme.
- **Abra com gancho concreto** (você + a vaga + um feito real). Nada de "Venho por meio desta".
- **Carta = 200–300 palavras**, estrutura Problema → Ação → Impacto, com 1 micro-episódio real
  (decisão/aprendizado) e fechamento com métrica + 1 pergunta específica sobre a vaga/empresa.
- **Métrica no lugar de adjetivo:** "reduzi 60%" > "melhorei muito".

## Banir (tells de IA)
- Palavras: delve/mergulhar, leverage/alavancar, robust/robusto, seamless, pivotal, foster,
  showcase, tapestry, synergy, cenário/landscape, "em constante evolução", "no mundo de hoje".
- Frases-clichê: "proven track record / histórico comprovado", "detail-oriented",
  "results-driven", "apaixonado por", "animado com a oportunidade de contribuir".
- Estruturas: regra de três em tudo, "não só X mas também Y", particípios empilhados
  (…aprimorando, fomentando, destacando), transições "Além disso/Ademais/Furthermore".
- Format: em dash em excesso, negrito decorativo, Title Case, bullets idênticos.

## Antes de entregar — checklist rápido
- [ ] Zero palavras/clichês banidos.
- [ ] Frases variam de tamanho; pelo menos 1 detalhe específico real por parágrafo.
- [ ] Carta tem micro-episódio real + métrica + pergunta sobre a vaga; 200–300 palavras.
- [ ] Keywords da vaga espelhadas (ATS) sem keyword stuffing.
- [ ] Idioma = idioma da vaga.
- [ ] Teste final: "um amigo reconheceria a voz dele aqui?" Se soa a modelo, reescreve.

> Esta skill é a fonte de verdade do estilo. O `ai/tailor.py` implementa estas mesmas regras no
> prompt do modelo; quando eu (Claude) escrever/revisar à mão, aplico isto diretamente.
