"""Descobre vagas numa plataforma, salva no banco e ranqueia contra o perfil.

Uso: python scripts/discover_rank.py [plataforma] [--keywords "appsec,pentest"] [--limit N]
Ex.: python scripts/discover_rank.py gupy --keywords "appsec,pentest,red team"

Ranquear usa o DeepSeek (reasoner) — pode levar ~30-60s por vaga ainda não ranqueada.
"""
from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session  # noqa: E402

from app.ai.eligibility import filter_eligible  # noqa: E402
from app.ai.ranker import rank_job  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.platforms import REGISTRY  # noqa: E402
from app.web.repo import get_or_create_profile, jobs_by_score, save_postings  # noqa: E402


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main() -> None:
    platform = sys.argv[1].lower() if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "gupy"
    if platform not in REGISTRY:
        raise SystemExit(f"Plataforma sem plugin: {platform}. Disponíveis: {list(REGISTRY)}")
    keywords = [k.strip() for k in _arg("--keywords", "appsec,pentest,red team,segurança da informação").split(",") if k.strip()]

    discover = import_module(f"app.platforms.{platform}.discovery").discover
    print(f"Descobrindo em {platform} | keywords={keywords}")
    postings = discover(keywords)  # cada plugin usa seus próprios defaults (limite/tenants)
    print(f"  {len(postings)} vaga(s) encontrada(s).")

    init_db()
    with Session(engine) as s:
        profile = get_or_create_profile(s)
        cv = profile.to_master_cv()

        # Descarte de vagas afirmativas exclusivas a grupos aos quais o candidato não pertence.
        postings, discarded = filter_eligible(postings, profile.demographics())
        if discarded:
            print(f"  {len(discarded)} descartada(s) por vaga afirmativa (fator imutável):")
            for p, res in discarded:
                print(f"    ✗ {p.title[:48]:48} | grupos={res.grupos} | {res.trecho[:45]}")

        saved = save_postings(s, postings)
        from app.config import settings
        to_rank = [j for j in saved if j.score is None]
        print(f"Ranqueando {len(to_rank)} vaga(s) nova(s) (model_rank={settings.model_rank})...")
        for j in to_rank:
            try:
                r = rank_job(cv, {"title": j.title, "company": j.company,
                                  "location": j.location, "description": j.description})
                j.score, j.score_reason, j.status = r.score, r.reason, "ranked"
                s.add(j)
                s.commit()
                print(f"  [{r.score:3}] {j.title[:55]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [erro] {j.title[:55]}: {exc}")

        print("\n=== Ranking (maior score primeiro) ===")
        for j in jobs_by_score(s):
            mark = f"{j.score:3}" if j.score is not None else "  -"
            print(f"[{mark}] {j.title[:50]:50} | {j.company[:20]:20} | {j.location[:16]}")


if __name__ == "__main__":
    main()
