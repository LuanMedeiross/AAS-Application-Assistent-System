# HUMANIZE — Writing applications that don't look AI-made

> **Critical document.** Every generated application text (summary, resume bullets, **cover
> letter**, form answers) MUST follow these rules. Text that "smells like AI" taints the
> application — recruiters reject it for looking generic/robotic. 2025–2026 research (sources at
> the end). Works alongside `ATS.md` (format/keywords) — this one is about the **human voice**.

## How AI text is detected (understand it to avoid it)

Detectors (GPTZero, Originality.ai, Turnitin) and experienced recruiters look for:

1. **Low perplexity** — predictable text, "always the expected word". A human surprises you.
2. **Low burstiness** — sentences all the same length/rhythm. A human mixes short and long.
3. **Lexical markers** — vocabulary and phrases that AI repeats (list below).
4. **Structural predictability** — uniform paragraphs, the "rule of three" everywhere, parallelisms.
5. **Absence of specific lived detail** — AI speaks generically; a human cites a tool, a number,
   a concrete episode.

> **Master rule:** no single signal is damning; it's the **cluster** that gives it away. The best
> disguise is not a trick — it's **real specificity** (something only you lived) + irregular rhythm.

## What NOT to write (AI tells)

**Burned vocabulary (avoid):** delve/mergulhar, leverage/alavancar, utilize/utilizar,
showcase/exibir, foster/fomentar, robust/robusto, seamless, pivotal, crucial, underscore,
tapestry, synergy, landscape/cenário, realm/âmbito, testament, vibrant, meticulous, embark,
endeavor, "game changer", "in today's world / no mundo de hoje", "in the ever-evolving / em
constante evolução", "fast-paced".

**Cover-letter cliché phrases (forbidden):**
- "I am writing to express my interest…" / "Venho por meio desta…" / "Escrevo para expressar
  meu interesse…"
- "proven track record" / "histórico comprovado", "detail-oriented professional" /
  "profissional orientado a detalhes", "results-driven", "team player"
- "I am excited about the opportunity to contribute to your team's success" / "Estou animado com
  a oportunidade de contribuir para o sucesso da equipe"
- "passionate about" / "apaixonado por" (without concrete proof right afterward)

**Structural patterns to avoid:**
- **Rule of three** everywhere ("fast, efficient, and scalable").
- **Negative parallelisms**: "não apenas X, mas também Y" / "not just… but also".
- **Stacked participles**: "…aprimorando X, fomentando Y, destacando Z".
- **Inflated verbs in place of "is/has"**: "serves as", "represents", "stands out as".
- **Formal transitions**: "Além disso", "Ademais", "Outrossim", "Furthermore", "Moreover".
- Paragraphs all the same length; grammar too perfect, without any personal touch.

**Punctuation/format:** **never use the em dash (—) or en dash (–) as punctuation or for an
aside.** It is an instant AI tell; rewrite with a comma, a period, or parentheses. (A dash inside a
numeric range like "200–300" is fine.) Don't use decorative bold in every sentence; don't use Title
Case in headings; don't stuff the text with identical bullets.

## What TO write (the human voice)

1. **Vary the rhythm (high burstiness).** Mix short sentences (5–8 words) with long ones (25–35).
   A short punchy sentence after a long one breaks the machine pattern.
2. **Be specific and concrete.** Name the tool, target, number, result. E.g.: instead of
   "worked with pentesting", write "exploited an IDOR in a REST API and escalated to account
   takeover; reported it with a PoC on HackerOne". A detail only you lived = undetectable.
3. **One micro-episode (30–60 words).** A real moment with a decision/tension: what was broken,
   what you did, what you learned. (No inventing — use facts from `master_cv`.)
4. **Contractions and natural language** (in the job's language). PT: not "tô", but avoid stuffy
   formality; prefer "o que me chamou aqui foi…" to "tenho a honra de…".
5. **Human transitions**: "o ponto é", "na prática", "foi aí que", "o que me puxou pra essa
   vaga". In English: "here's what I mean", "the thing is".
6. **Concrete metric** instead of an adjective: "cut response time by 60%" > "significantly
   improved performance".
7. **Opening hook** that cites the job + a real project/achievement of yours — no "Venho por meio
   desta".
8. **Mirror the job as genuine interest.** Pick up the areas, technologies, and responsibilities
   from the job description and frame them as the candidate's real interest and desire to grow
   (including areas they haven't explored much yet), always honestly as motivation to learn, never
   as experience they lack. It proves they actually read the posting.

## Cover-letter-specific rules

- **Length:** 200–300 words. A long, uniform letter looks like AI and tires the recruiter.
- **Problem → Action → Impact structure:** open with a concrete hook (you + the job), tell a real
  achievement tied to what the job asks for, close with a metric and **a specific question about
  the job/company** (shows you actually read it).
- **Connect it to the real:** every generic claim must become a scene + a number (see `ATS.md` —
  amplify real competence, never fabricate facts).
- **Don't reference the employer at all.** In narrative text (cover letter, form answers), do NOT
  mention the employer in any form (not the name, not a generic reference like "at a tech company"
  or "in my current job"). State the experience directly, in first person and by what was done:
  "I run internal pentests…", "I've found critical flaws…". Only mention an employer if the
  question explicitly asks. The structured CV keeps company names as usual; this rule is about the
  prose.
- **Language = job language** (the tailor's rule). Apply these principles in the right language.

## Checklist the tailor applies to EACH generated text

- [ ] Zero words from the burned list; zero cover-letter cliché phrases.
- [ ] Sentences vary in length (there's a short one and a long one) — no uniform rhythm.
- [ ] At least 1 real specific detail (tool/target/number) per paragraph.
- [ ] 1 concrete micro-episode in the letter (decision/lesson), based on a real fact.
- [ ] No repetitive rule of three, no "not just… but also" parallelism, no stacked participles.
- [ ] Cliché-free opening; closing with a metric + a specific question about the job.
- [ ] No employer mentioned at all in narrative text (name or generic), unless the question asks.
- [ ] Letter between 200–300 words; **zero em/en dashes (—, –)** as punctuation; no decorative bold.
- [ ] Sounds like the person speaking, not like a model. (Test: "would a friend recognize my voice?")

## Relationship with `ATS.md`

`ATS.md` ensures the robot (parser) **reads and ranks**; `HUMANIZE.md` ensures the human
(recruiter) **doesn't get suspicious**. The two together: correct keywords and format **and** a
natural voice. In a conflict, real specificity resolves both — a true keyword told as a scene
becomes a match in the ATS and human proof at the same time.

## Sources
- [Como detectores de IA usam perplexidade e burstiness — Hastewire](https://hastewire.com/blog/how-ai-detectors-calculate-perplexity-and-burstiness)
- [How AI Detectors Work — GPTZero](https://gptzero.me/news/how-ai-detectors-work/)
- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- [27 Signs of AI Writing — vrid.ai](https://vrid.ai/blog/signs-of-ai-writing)
- [Most Common ChatGPT Words to Avoid — Walter Writes](https://walterwrites.ai/most-common-chatgpt-words-to-avoid/)
- [Avoid AI Detection: Authentic Cover Letters 2026 — WahResume](https://www.wahresume.com/blog/avoid-ai-detection-writing-authentic-cover-letters-in-2026)
- [Can Employers Tell If You Use AI for a Cover Letter? — AiApply](https://aiapply.co/blog/can-employers-tell-if-you-use-ai-for-a-cover-letter)
- [AI Detection in Cover Letters — Originality.ai](https://originality.ai/blog/ai-detection-cover-letters)
