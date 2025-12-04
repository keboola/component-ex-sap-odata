# TODO List - SAP OData Component

## ✅ COMPLETED: URL Structure Analysis & Configuration Refactoring
- [x] Analyzovat strukturu SAP OData URL (viz `docs/URL_STRUCTURE_ANALYSIS.md`)
  - V2: `{base_url}/sap/opu/odata/sap/{service_name}`
  - V4: `{base_url}/sap/opu/odata4/sap/{service_group}/.../{version}`
  - Identifikovány variable vs fixed části
- [x] Implementovat hybridní přístup (backward compatible):
  - **Option 1 (Legacy)**: `service_url` - plná URL jako dříve
  - **Option 2 (New)**: `base_url` + `service_path` - oddělené části
  - Gateway path (`/sap/opu/odata/sap/` nebo `/sap/opu/odata4/sap/`) se přidává automaticky
- [x] Aktualizovat Configuration model:
  - Přidány `base_url` a `service_path` jako optional
  - `service_url` je nyní optional (backward compatible)
  - Validace zajistí že se použije právě jedna metoda
  - `get_service_url()` metoda pro konstrukci URL
  - Automatická detekce V2/V4 z service_path struktury
- [x] Aktualizovat JSON schema (configSchema.json)
- [x] Vytvořit nové sample configs:
  - `config.sample.v2-split-url.json`
  - `config.sample.v4-split-url.json`
- [x] Aktualizovat dokumentaci v `data/README.md`
- [x] Přidat 10 nových unit testů pro URL konfiguraci (59 testů celkem, všechny passed)

## ✅ COMPLETED: Data Directory & Git Security
- [x] Opravit `.gitignore`:
  - Celá složka `data/` je ignorována
  - Výjimky: `data/README.md` a `data/config.sample*.json`
  - Správně ignoruje `data/config.json`, `data/state.json`, `data/out/`, `data/in/`
- [x] Vyčistit repository:
  - Odstraněn `data/config.json` s potenciálními credentials
  - Sample configs zůstávají v `data/` (lépe viditelné pro uživatele)
- [x] Dokumentace v `data/README.md` vysvětluje:
  - Jaké soubory patří do `data/` při vývoji
  - Co nesmí být commitnuto
  - Dva způsoby URL konfigurace

## ✅ COMPLETED: Functional/Integration Tests s DataDir
- [x] Nastudovat příklad datadir-tests pattern
- [x] Vytvořit strukturu pro funkční testy:
  - `tests/functional/test_functional.py` - pytest funkční testy
  - Testy pro OData V2 a V4 s reálným SAP API
  - Testy pro oba URL přístupy (service_url vs base_url+service_path)
  - Testy pro chybové stavy (invalid credentials)
- [x] Environment variable pattern:
  - `SAP_API_KEY` environment variable
  - Pytest skipif decorator pokud není k dispozici
  - `.env.example` soubor pro lokální development
- [x] Dokumentace:
  - `docs/DEVELOPMENT.md` - kompletní development guide
  - Jak získat SAP API key z api.sap.com
  - Příklady různých SAP APIs (V2/V4, Company Code, Fixed Asset, atd.)
  - Troubleshooting sekce
- [x] GitHub Actions workflow:
  - Aktualizován `.github/workflows/push.yml`
  - Unit testy běží vždy
  - Funkční testy běží pouze pokud je `SAP_API_KEY` secret nastaven
- [x] README aktualizace:
  - Dokumentace obou URL přístupů
  - Odkazy na development guide
  - Příklady testování

## Notes
- Priorita: 1 (URL struktura) → 2 (Git security) → 3 (Funkční testy) → 4 (Docs)
- Před začátkem práce na testech analyzovat více SAP OData URL příkladů
- Zvážit podporu různých SAP deployment modelů (Cloud vs On-Premise)
