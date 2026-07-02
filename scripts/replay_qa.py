"""Replay recorded screening-form questions through the AI, offline.

Once an application has gone through the apply flow it carries a recorded Q&A in
`Application.form_qa` (the questions the company asked + what the AI answered). This tool
re-injects ONLY the questions into the form agent (DeepSeek) and prints the answers it produces
now. No browser, no platform, no submission: use it to test prompt/rule changes (HUMANIZE, the
em-dash / employer / interest rules, etc.) against real questions without burning a live
application.

Usage:
    python scripts/replay_qa.py                 # list applications that have a recorded Q&A
    python scripts/replay_qa.py <job_id>        # replay: the AI answers the recorded questions
    python scripts/replay_qa.py <job_id> --dry  # show the questions that WOULD be injected (no API call)

Only DeepSeek is called (costs tokens); nothing touches a job platform. `--dry` calls nothing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.core.form_extract import FormQuestion  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Application, Job  # noqa: E402
from app.web.repo import get_or_create_profile  # noqa: E402


def _synth_key(record: dict, index: int) -> str:
    """Stable key for the round-trip. Old captures (pre-enrichment) have no key; synthesize one so
    the form agent can match its answers back to each question."""
    return record.get("key") or f"q{index}"


def _rebuild(records: list[dict]) -> list[FormQuestion]:
    """Rebuild FormQuestion objects from stored form_qa records (enough for a faithful replay)."""
    return [
        FormQuestion(
            key=_synth_key(r, i),
            prompt=r.get("question", ""),
            kind=r.get("kind", "text"),
            options=r.get("options") or [],
            required=bool(r.get("required")),
            max_select=int(r.get("max_select") or 0),
        )
        for i, r in enumerate(records)
    ]


def _list_applications(session: Session) -> None:
    jobs = {j.id: j for j in session.exec(select(Job)).all()}
    found = False
    for a in session.exec(select(Application)).all():
        if a.form_qa:
            found = True
            j = jobs.get(a.job_id)
            title = f"{j.title} @ {j.company}" if j else "?"
            print(f"  job {a.job_id}: {title} — {len(a.form_qa)} pergunta(s) gravada(s)")
    if not found:
        print("Nenhuma candidatura com Q&A gravado ainda. Rode uma candidatura para capturar as perguntas.")


def _replay(session: Session, job_id: int, dry: bool) -> None:
    app_row = session.exec(select(Application).where(Application.job_id == job_id)).first()
    if not app_row or not app_row.form_qa:
        raise SystemExit(f"Sem Q&A gravado para a vaga {job_id}. (rode sem argumentos para listar)")
    job = session.get(Job, job_id)
    profile = get_or_create_profile(session)

    # Group by step to mirror the real per-step calls (company questions, then personalize).
    steps: dict[str, list[dict]] = {}
    for r in app_row.form_qa:
        steps.setdefault(r.get("step", "?"), []).append(r)

    cover = ""
    if app_row.cover_letter_path and Path(app_row.cover_letter_path).exists():
        cover = Path(app_row.cover_letter_path).read_text(encoding="utf-8")
    job_d = {"title": job.title, "company": job.company, "description": job.description} if job else {}

    for step, records in steps.items():
        questions = _rebuild(records)
        print(f"\n=== step: {step} ({len(questions)} pergunta(s)) ===")

        if dry:
            for q in questions:
                opts = f" opts={q.options}" if q.options else ""
                print(f"  [{q.key}] ({q.kind}) req={q.required}{opts} :: {q.prompt}")
            continue

        # Real replay: this is the only place that hits DeepSeek (import lazily so --dry is free).
        from app.ai import form_agent

        plan = form_agent.map_form(
            questions, profile=profile.to_master_cv(), cover_letter=cover,
            job=job_d, extras=profile.to_application_extras(),
        )
        answers_by_key = {a.key: a for a in plan.answers}
        unknown_set = set(plan.unknown)
        # Iterate over every question so nothing is silently missing (even choices dropped for
        # lacking recorded options are shown with a hint).
        for i, r in enumerate(records):
            k = _synth_key(r, i)
            print(f"\n  Q ({r.get('kind')}): {r.get('question', k)}")
            a = answers_by_key.get(k)
            if a is not None:
                print(f"  NOVA → {a.value}  ({a.confidence})")
            elif k in unknown_set:
                print("  NOVA → [unknown / deixada para revisão humana]")
            else:
                print("  NOVA → (sem resposta; provável escolha/skills sem opções gravadas)")
            if r.get("answer"):
                print(f"  ANTIGA → {r.get('answer')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay recorded form questions through the AI (offline).")
    ap.add_argument("job_id", nargs="?", type=int, help="Job id whose recorded questions to replay.")
    ap.add_argument("--dry", action="store_true", help="Show the questions without calling DeepSeek.")
    args = ap.parse_args()

    init_db()
    with Session(engine) as session:
        if not args.job_id:
            _list_applications(session)
        else:
            _replay(session, args.job_id, args.dry)


if __name__ == "__main__":
    main()
