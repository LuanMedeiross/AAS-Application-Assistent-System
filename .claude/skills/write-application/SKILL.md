---
name: write-application
description: Use ALWAYS when writing or reviewing any job application text — cover letter, resume summary, experience bullets, or application form answers. Ensures a human voice (not detectable as AI) + ATS format. Triggers - "write the letter", "generate the CV", "tailor the resume", "answer the job form", "application text", "cover letter".
---

# Writing an application (human voice + ATS)

Every time I produce text that goes to a recruiter, I follow this process. Dual goal:
**pass the ATS** (a bot reads/ranks it) and **not sound like AI** (a human doesn't get suspicious). The full
rules live in `ATS.md` and `HUMANIZE.md` at the project root — read them when you need the
detail; the essentials are here.

## Non-negotiable principles

1. **Real specificity is the best disguise.** Every generic claim becomes a scene + number, with
   a tool/target/result the person actually experienced (source: `curriculum/master_cv.json`).
2. **Amplify competence, never fabricate fact.** You can highlight/go deeper on real skills; don't
   invent employment, seniority, or certification (see `ATS.md`).
3. **Language = the job's language.** Detect and write in the same language as the description.

## Before writing
- Read the job description; extract the exact keywords (to mirror — ATS).
- Pull from the `master_cv` the most relevant real facts (projects, bug bounty, labs, metrics).
- Set the language by the description.

## While writing
- **Vary the rhythm:** mix short sentences (5–8 words) and long ones (25–35). Never uniform.
- **Open with a concrete hook** (you + the job + a real accomplishment). No "I am writing to you regarding".
- **Cover letter = 200–300 words**, Problem → Action → Impact structure, with 1 real micro-episode
  (decision/lesson) and a closing with a metric + 1 specific question about the job/company.
- **Metric instead of adjective:** "reduced by 60%" > "improved a lot".

## Ban (AI tells)
- Words: delve/mergulhar, leverage/alavancar, robust/robusto, seamless, pivotal, foster,
  showcase, tapestry, synergy, cenário/landscape, "ever-evolving", "in today's world".
- Cliché phrases: "proven track record / histórico comprovado", "detail-oriented",
  "results-driven", "passionate about", "excited about the opportunity to contribute".
- Structures: rule of three everywhere, "not only X but also Y", stacked participles
  (…improving, fostering, highlighting), "Furthermore/Moreover/Additionally" transitions.
- Format: overuse of em dashes, decorative bold, Title Case, identical bullets.

## Before delivering — quick checklist
- [ ] Zero banned words/clichés.
- [ ] Sentences vary in length; at least 1 specific real detail per paragraph.
- [ ] Cover letter has a real micro-episode + metric + question about the job; 200–300 words.
- [ ] Job keywords mirrored (ATS) without keyword stuffing.
- [ ] Language = the job's language.
- [ ] Final test: "would a friend recognize their voice here?" If it sounds like a model, rewrite.

> This skill is the source of truth for the style. `ai/tailor.py` implements these same rules in
> the model's prompt; when I (Claude) write/review by hand, I apply this directly.
