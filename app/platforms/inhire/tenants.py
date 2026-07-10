"""Curated InHire tenant slugs (companies whose career pages run on InHire).

InHire has **no global job search** — discovery must target known company tenants via the
`X-Tenant` header (see INHIRE.md §1). This list is that seed, and it lives in the plugin (not in
`.env`) because it is a stable, shared asset worth versioning.

Every slug here was **validated live against the API** (`GET /tenants/public/resolve/<slug>`) at
compile time; comments mark the sector and, where relevant, `# (no open roles at last scan)` for
tenants that resolved but had 0 published jobs then (kept because they post periodically).

Maintenance: to add a company, confirm `https://<slug>.inhire.app/vagas` loads (or the resolve
endpoint returns its `<tenant>`), then drop the slug in the right bucket. `INHIRE_TENANTS` in
`.env` still works and **extends** this list (see `discovery.py`).
"""
from __future__ import annotations

# Cybersecurity + big-4 cyber/audit consultancies — PRIMARY target for this profile.
CYBER_SECURITY = [
    "tempest",   # Tempest Security Intelligence (largest BR cyber pure-play)
    "clavis",    # Clavis Segurança da Informação (offensive/MSS)
    "asper",     # Asper (MSSP)
    "deloitte",  # Deloitte (has a Cyber/Pentest practice, Recife/SP)
    "kpmg",      # KPMG (cyber/advisory among audit roles)
]

# IT consultancies, software houses, dev shops, R&D institutes.
TECH_SERVICES = [
    "grupotaking", "radix", "frameworkdigital", "dtidigital", "venturus", "ipnet", "deal",
    "indicium", "qive", "ctctech", "exa", "programmers", "objective", "sidia", "indt", "sysmap",
    "semantix",  # data/AI
    "st-one",    # industrial IoT
    "elsys",     # electronics/IoT
    "lwsa",      # Locaweb Company (hosting/cloud/e-commerce infra)
    "auvotecnologia",  # field-service SaaS
    "encora", "ciandt", "zup",  # (no open roles at last scan)
]

# Fintech, payments, banking, identity.
FINTECH = [
    "cielo", "dock", "qitech", "celcoin", "klavi", "warren", "avenue", "kanastra", "cora", "pier",
    "foxbit", "idwall", "unico", "inco", "monkey",
    "contasimples", "creditas", "ebanx", "meliuz", "nomad", "nubank", "stone", "willbank", "flash",
    # ^ (no open roles at last scan)
]

# SaaS / product companies.
SAAS = [
    "contaazul", "superlogica", "nibo", "paytrack", "v360",
    "clicksign", "zenvia",  # (no open roles at last scan)
]

# Edtech.
EDTECH = [
    "vitru", "sanar", "queroeducacao", "pravaler", "principia",
    "cogna", "letrus",  # (no open roles at last scan)
]

# E-commerce, marketplaces, mobility, media, creator economy.
ECOMMERCE_MOBILITY = [
    "olist", "enjoei", "instacarro", "daki", "cobli", "frete", "estapar", "magazineluiza",
    "winnin", "livemode", "kiwify", "rpo-abinbev",
    "ifood", "loggi", "tembici", "dafiti", "unidas", "tray", "linx", "loft", "livup",  # (empty at scan)
]

# Health-tech.
HEALTH = ["alice", "telavita"]

# Benefits, HR/recruiting, industrial/logistics (non-tech but confirmed InHire tenants).
OTHER = [
    "vr", "alelo",                 # benefits
    "leaderetalent", "trinnus",    # HR/recruiting
    "priner", "santosbrasil",      # industrial services / port logistics
]

# Flat, de-duplicated master list (order = priority: cyber first).
TENANTS = list(dict.fromkeys(
    CYBER_SECURITY + TECH_SERVICES + FINTECH + SAAS + EDTECH + ECOMMERCE_MOBILITY + HEALTH + OTHER
))
