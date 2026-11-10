# Illona

Illona conectează un client AI cu Adobe Illustrator stabil, pe macOS, pentru ilustrații vectoriale editabile, logo-uri, texte, imagini și broșuri.

**86 de instrumente MCP:** 16 Illona, 66 Pro adaptate din IE3 și patru pentru biblioteca Creold. Sunt incluse **104 scripturi originale Creold** și **14 acțiuni cu parametri direcți**, inclusiv trasarea imaginilor în vectori. Serverul rulează local prin stdio, AppleScript și ExtendScript; nu cere Illustrator Beta.

Acest repository conține serverul, bibliotecile necesare, skill-ul, regulile și ghidurile generale. Conversațiile, lucrările personale, imaginile de proiect și jurnalele de sesiune nu fac parte din distribuție.

## Instalare pe alt Mac

Ai nevoie de Adobe Illustrator instalat și licențiat, Python 3.11+ și Node.js 20+. Serverul nu cere o cheie OpenAI sau credențiale Adobe în configurația sa.

1. Descarcă repository-ul prin **Code → Download ZIP**, apoi dezarhivează-l. Alternativ, clonează repository-ul:

```sh
git clone https://github.com/adancu98/illona.git
cd illona
```

2. Deschide Terminal în directorul `illona` și instalează dependențele:

```sh
sh setup.sh
```

Dacă `python3` este prea vechi, indică un Python compatibil instalat, de exemplu:

```sh
ILLONA_PYTHON=python3.12 sh setup.sh
```

3. Înregistrează serverul în Codex, din același director:

```sh
codex mcp add illona -- /bin/sh "$PWD/run.sh"
codex mcp list
```

Pentru un alt client MCP, configurează transportul **stdio**, comanda `/bin/sh` și un singur argument: calea absolută către `run.sh`. Nu publica fișierul personal de configurare al clientului.

La primul apel, macOS poate cere permisiunea aplicației gazdă de a controla Illustrator, în **System Settings → Privacy & Security → Automation**. Deschide Illustrator și începe cu `illona_status`.

`run.sh` este un server MCP, nu o interfață interactivă de terminal. Clientul AI îl pornește automat.

## Skill și reguli

- [Skill Illona](.agents/skills/illona/SKILL.md): fluxuri pentru ilustrații, logo-uri, tipografie, broșuri și vectorizare.
- [AGENTS.md](AGENTS.md): reguli tehnice pentru agenți și dezvoltare.
- [Biblioteca de practică](docs/learning-playbook.md): proceduri generale bazate pe lecții Adobe, fără istoricul lucrărilor.
- [Integrarea Creold](docs/creold-integration.md): catalog, cele 14 acțiuni și limitele originalelor cu dialog.
- [Inventarul Pro](docs/ie3-function-parity.md): toate cele 66 de instrumente Pro.

Când deschizi acest repository în Codex, skill-ul se află în directorul standard `.agents/skills`. Îl poți invoca explicit cu **`$illona`**. Skill-ul oferă instrucțiuni; conectarea serverului MCP rămâne necesară.

Resursele oferite chiar de MCP sunt `illona://design-guide`, `illona://learning-playbook` și `illona://creold-guide`.

## Ce poate face

| Familie | Capacități |
| --- | --- |
| Illona | Documente, forme, Bézier, texte, imagini, ilustrații, broșuri, preview, preflight și salvare/export |
| Pro | Grupuri, aliniere, gradienți, straturi, artboarduri, stiluri, simboluri, SVG, imagini și operații de producție |
| Creold | Catalogul original, lansare cu dialog și 14 adaptări: degradeuri, contururi, culori, coordonate, puncte, baseline, opacitate și trasare |

Nu toate cele 104 originale rulează automat. Multe cer dialogul lor în Illustrator. Pentru lucru fără dialog folosește acțiunile parametrizate; `script_returned` la un original nu confirmă singur modificarea.

## Convenții importante

- Obține documentul prin `illona_status`; editează numai `document_id` și UUID-urile explicite.
- Instrumentele de bază folosesc implicit **mm**, cu originea în colțul stânga sus și Y în jos.
- Instrumentele Pro folosesc **puncte**, implicit `artboard-web`, Y în jos. Inspecția nativă și acțiunile Creold folosesc puncte ale documentului, Y în sus.
- Dimensiunea fontului, leadingul și grosimea conturului sunt în puncte.
- Verifică vizual fiecare rezultat. Trasarea este o aproximație vectorială a sursei și nu reconstruiește detalii care lipsesc din fotografie.
- Păstrează un `operation_id` stabil. După timeout consultă `illona_operation_status`; nu repeta o modificare cu rezultat incert.
- Salvarea AI păstrează documentul complet. Exportul de bază produce o copie a unui artboard; exportul PDF verifică TrimBox/BleedBox. Preflight-ul este consultativ și nu certifică PDF/X sau acceptarea la tipografie.

## Configurare

| Variabilă | Rol |
| --- | --- |
| `ILLONA_APP_PATH` | Calea instalării Illustrator; implicit `/Applications/Adobe Illustrator 2026/Adobe Illustrator.app` |
| `ILLONA_OUTPUT_DIR` | Directorul rezultatelor; implicit `output/` în proiect |
| `ILLONA_STATE_DIR` | Cereri, rezultate și blocare; implicit `.illona-state/` |
| `ILLONA_NODE` | Calea Node.js 20+, dacă nu este disponibil în PATH |
| `ILLONA_TIMEOUT_SECONDS` | Așteptarea bridge-ului; un timeout nu garantează anularea nativă |
| `ILLONA_PYTHON` | Python folosit de `setup.sh` |

Starea, previzualizările, fișierele exportate și setările locale se creează doar pe calculatorul fiecărui utilizator și sunt excluse prin `.gitignore`. Păstrează directorul de stare cât timp o operație are rezultat neclar.

## Verificare offline

```sh
.venv/bin/python -m pytest -q
node tests/host_core_test.cjs
node --test tests/creold_host.test.cjs tests/creold_trace.test.cjs
```

Testele folosesc simulări și verificări ale catalogului; nu pornesc Illustrator. Comparația suplimentară cu un checkout upstream este opțională. Catalogul și hash-urile fișierelor împachetate sunt verificate și fără acel checkout.

Adaptorul Node este inclus în `illona_mcp/ie3_runtime/adapter.cjs` și rulează fără npm sau `node_modules`. Biblioteca Creold și fișierele sale auxiliare sunt în `illona_mcp/creold_runtime`.

## Surse și licențe

Componentele terțe păstrează licențele și atribuirea lor: [notificări complete](THIRD_PARTY_NOTICES.md). Biblioteca Creold include un fișier AI auxiliar și un GIF oficial necesare inventarului original; acestea nu sunt lucrări ale utilizatorului.

- [IE3 Illustrator MCP](https://github.com/ie3jp/illustrator-mcp-server)
- [Creold Illustrator Scripts](https://github.com/creold/illustrator-scripts)
- [Adobe Illustrator scripting](https://developer.adobe.com/illustrator/)
- [Configurare MCP în Codex](https://developers.openai.com/codex/mcp/)
- [Skills în Codex](https://developers.openai.com/codex/skills/)

Illona nu este un produs Adobe, IE3, Creold sau OpenAI și nu implică aprobarea acestora.
