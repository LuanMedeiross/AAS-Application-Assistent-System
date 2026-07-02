# curriculum/

Seu CV-mestre mora aqui. **Os arquivos reais NÃO vão para o git** (ver `.gitignore`) —
cada pessoa mantém o seu localmente. Só `*.example.json` e este README são versionados.

## Como popular

1. Copie o exemplo:
   ```bash
   cp curriculum/master_cv.example.json curriculum/master_cv.json
   ```
2. Edite `curriculum/master_cv.json` com seus dados reais (é a fonte de verdade do conteúdo
   que a IA usa para ranquear vagas e gerar CV/carta sob medida).
3. Rode o seed para carregar no banco:
   ```bash
   python scripts/seed_profile.py
   ```

Alternativa: importe do export oficial do LinkedIn com `scripts/import_linkedin.py`.

## Arquivos (todos ignorados pelo git, exceto os de exemplo)

- `master_cv.json` — perfil estruturado (fonte de verdade). **Contém dados pessoais.**
- `curriculo.md` / `curriculo.pdf` — versões geradas/de referência do seu CV.
