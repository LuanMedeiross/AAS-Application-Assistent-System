# curriculum/

Your master CV lives here. **The real files do NOT go to git** (see `.gitignore`) —
each person keeps their own locally. Only `*.example.json` and this README are versioned.

## How to populate

1. Copy the example:
   ```bash
   cp curriculum/master_cv.example.json curriculum/master_cv.json
   ```
2. Edit `curriculum/master_cv.json` with your real data (it is the source of truth for the content
   the AI uses to rank jobs and generate a tailored CV/cover letter).
3. Run the seed to load it into the database:
   ```bash
   python scripts/seed_profile.py
   ```

Alternative: import from the official LinkedIn export with `scripts/import_linkedin.py`.

## Files (all ignored by git, except the example ones)

- `master_cv.json` — structured profile (source of truth). **Contains personal data.**
- `curriculo.md` / `curriculo.pdf` — generated/reference versions of your CV.
