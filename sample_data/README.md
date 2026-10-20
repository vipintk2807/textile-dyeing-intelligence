# Synthetic sample data

Everything loaded by `scripts/load_sample_data.py` is **synthetic and illustrative**.
It is not real factory data, not a validated dyeing recipe and not a production benchmark.
All identifiers start with `SYN-` (machines `SYN-M01..`, recipes `SYN-R01..`, batches
`SYN-B001..`) and notes say "SYNTHETIC EXAMPLE".

Load into a separate demo database (recommended):

    python scripts/load_sample_data.py --db demo.db
    set TDI_DB_PATH=demo.db   (then start the app)

The loader refuses to run twice and refuses to add into a database that holds real records.
To remove only the sample records again: `python scripts/load_sample_data.py --db demo.db --remove`.

Covered cases: several batch statuses, two recipes with three revisions, a +20 % consumption
variance, zero planned quantity, missing actual quantity, incompatible units (kg vs g), a
pending inspection, a failed inspection followed by rework and a passing follow-up, unresolved
rework, a batch with no machine/inspection, and a cancelled batch.
