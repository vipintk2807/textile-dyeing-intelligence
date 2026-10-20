# Textile Dyeing Intelligence

A local-first record-keeping and analysis tool for textile dyeing batches. It runs on your own
computer, stores data in a single SQLite file and has no cloud service, login or telemetry.

It records what was planned and what happened (batches, recipes and revisions, machines,
process observations, planned vs actual chemical consumption, quality inspections and rework)
and reports on it. It does **not** control machines, predict outcomes or recommend recipes.

> Sample data shipped with the project is **synthetic** (every identifier starts with `SYN-`).
> It is for demonstration only and is never loaded unless you ask for it.

## Features

- **Batches**: create, edit, search; status flow planned → in progress → completed / cancelled.
  Completed and cancelled batches lock quantity, recipe revision and machine.
- **Recipes**: recipes with immutable revisions (a revision used by a batch can never change).
- **Machines**: catalogue with a recorded administrative status.
- **Process records**: manually entered observations with observed-at and recorded-at times;
  corrections keep history.
- **Chemical consumption**: planned and actual quantities with variance (actual − planned and %).
- **Quality inspections**: pending → passed / failed; finalised inspections are immutable.
- **Rework**: linked to a batch and optionally an inspection.
- **Dashboard and Reports**: filters, six reports, CSV export.
- **Backup and restore** scripts; **sample data** loader/remover.

## Requirements

- Python 3.11 or newer (tested on Python 3.13), Windows 10/11 recommended.
- Free, open-source packages only: Streamlit, Pydantic (runtime); pytest, Ruff (development).
- No GPU, no paid service.

## Setup on Windows (Command Prompt)

Open **Command Prompt** (CMD) in the project folder:

```
cd path\to\textile-dyeing-intelligence
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Your browser opens at `http://localhost:8501`. Stop the app with `Ctrl+C` in the CMD window.

PowerShell: activate with `.venv\Scripts\Activate.ps1` (if scripts are blocked, use CMD instead).

Next time, only run `.venv\Scripts\activate.bat` and `streamlit run app.py`.

## Where the data is stored

Windows: `%LOCALAPPDATA%\TextileDyeingIntelligence\textile_dyeing.db`
(elsewhere: `~/.local/share/textile-dyeing-intelligence/`). The file is created on first start.

To use another file:

```
set TDI_DB_PATH=C:\data\my_dyeing.db
streamlit run app.py
```

## Sample data (optional)

```
python scripts\load_sample_data.py
python scripts\load_sample_data.py --remove
```

Loading is refused if sample data is already present. `--remove` deletes only `SYN-` records.
Use `--db PATH` to target a specific file. See `sample_data\README.md`.

## Backup and restore

```
python scripts\backup_db.py --out backups\before_change.db
python scripts\restore_db.py backups\before_change.db
```

Close the app before restoring. The current database is first copied to
`<name>.pre-restore-<timestamp>`; the backup is integrity-checked before use.
Real databases and backups are excluded from Git by `.gitignore`.

## Tests and lint

```
pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
```

## How figures are defined

- **Variance** = actual − planned; **variance %** = (actual − planned) / planned × 100.
  Shown as *Unavailable* when planned is 0, either value is missing, or units/basis differ.
  No unit conversion is ever applied.
- **Final quality outcome** of a batch = latest finalised (passed/failed) inspection. Pending
  inspections are ignored; no inspection is *not* a pass.
- **Failure rate** = batches whose final outcome is failed / batches with a final outcome.
- **Rework rate** = batches with at least one non-cancelled rework / non-cancelled batches.
  Rework events are reported separately.
- **Batch reporting date** = actual start date, else planned date, else creation date.
- Quantities use exact decimals (max 15 integer digits, 6 decimal places). Times are local,
  without time zone. No thresholds or recipes are invented by the application.
- **CSV export** is UTF-8 with BOM (opens correctly in Excel). Text cells starting with
  `= + - @` get a leading `'` to prevent spreadsheet formula injection.

## Troubleshooting

- `streamlit` not recognised: activate the venv (`.venv\Scripts\activate.bat`).
- Port in use: `streamlit run app.py --server.port 8502`.
- "The database could not be opened": check the folder exists and is writable, or the file is a valid DB.
- Restore a previous state with `scripts\restore_db.py`.

## Known limitations

- Automated tests were run on Linux with Python 3.13 only; **not yet run on Windows**.
- Single-user, no authentication; do not expose the app to a network.
- SQLite file is not encrypted.
- Manual data entry only (no import, machine integration, ML or telemetry).
- No unit conversion; user interface is English only.

## Publishing to GitHub (account `vipintk2807`)

You use more than one GitHub account, so check identity before committing. Never paste
passwords, tokens or private keys anywhere.

1. Create an empty repository `textile-dyeing-intelligence` on GitHub while signed in as `vipintk2807`
   (no README/licence, as they exist here).
2. In the project folder:
   ```
   git init -b main
   git config user.name "Vipin T K"
   git config user.email "YOUR-EMAIL-FOR-THIS-ACCOUNT"
   git config --local --list | findstr user
   git status
   ```
   Confirm `git status` does not list any `.db` file, `.venv` or private planning documents.
3. Remote (only if you have an SSH host alias named `github-vipintk2807` in `%USERPROFILE%\.ssh\config`):
   ```
   ssh -T git@github-vipintk2807
   git remote add origin git@github-vipintk2807:vipintk2807/textile-dyeing-intelligence.git
   git remote -v
   ```
   The `ssh -T` greeting must name `vipintk2807`. If it names another account, stop and fix your SSH
   config; otherwise use HTTPS: `https://github.com/vipintk2807/textile-dyeing-intelligence.git`.
4. Commit and push:
   ```
   git add .
   git commit -m "Initial commit: Textile Dyeing Intelligence"
   git push -u origin main
   ```

## Licence

MIT, copyright Vipin T K. See `LICENSE`.
