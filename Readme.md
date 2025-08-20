## Cloud Bucket Browser (S3/GCS): View CSV/XLS(X) as Tables and Graphs

A Streamlit app to browse cloud buckets, preview tabular data, and render up to two files side‑by‑side as charts.

### Features
- Browse `gs://` (Google Cloud Storage) and `s3://` (AWS S3) prefixes.
- Show only `.csv`, `.xls`, `.xlsx` files per folder.
- Select up to 2 files; displays data table + chart for each in side‑by‑side columns.
- Auto charting:
  - Time‑series when columns `Frame Number`, `Procrustes Similarity`, `Joint Angle Distance` exist.
  - Otherwise, uses a simple heuristic: bar chart for one categorical + one numeric column, else line chart for numeric columns.
- Auth options:
  - GCS: Public (anonymous), Service Account JSON upload, or Google Application Default Credentials (ADC).
  - S3: Public (anonymous) or AWS access keys (+ optional region).

---

## Requirements
- Python 3.9+ recommended
- Dependencies in `requirements.txt`:
  - `streamlit`, `pandas`, `plotly`, `openpyxl`, `matplotlib`, `s3fs`, `gcsfs`

---

## Setup (Windows/PowerShell)
```powershell
cd D:\Movrs\Movrs_GraphRepresentation\Old
python -m venv .venv

# If activation is blocked, EITHER run the first line for this session only, or the second to set per-user
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
# Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force

.\.venv\Scripts\Activate
pip install -r requirements.txt
```

### macOS/Linux
```bash
cd /path/to/Movrs_GraphRepresentation/Old
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Run
```powershell
# In the activated venv
python -m streamlit run app.py

# If you chose not to activate the venv
.\.venv\Scripts\python -m streamlit run app.py
```

Open the URL shown (usually `http://localhost:8501`).

---

## Usage
1. In the left sidebar, enter a bucket or prefix:
   - GCS example: `gs://msp-1/test/`
   - S3 example: `s3://my-bucket/some/prefix/`
2. Choose auth:
   - GCS:
     - Public: check “Public (anonymous)”.
     - Private: uncheck Public, upload Service Account JSON, then Connect.
     - Or use Google ADC (no upload): run `gcloud auth application-default login` and leave Public unchecked.
   - S3:
     - Public: check “Public (anonymous)”.
     - Private: uncheck Public, enter AWS keys (and region if needed), then Connect.
3. Browse folders; only `.csv/.xls/.xlsx` show in Files.
4. Select up to 2 files → click “Load and visualize”.
5. Each selected file displays a 50‑row preview and a chart, side‑by‑side.

---

## Authentication Notes

### Google Cloud Storage (gs://)
- Service Account JSON upload: Use a key with at least `roles/storage.objectViewer` for the bucket/prefix.
- Application Default Credentials (no upload): 
  ```powershell
  gcloud auth application-default login
  ```
- Environment variable alternative:
  ```powershell
  $env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\service-account.json"
  ```

### AWS S3 (s3://)
- Provide `AWS Access Key ID` and `AWS Secret Access Key` (and optional session token/region).
- Public buckets can be browsed with the “Public (anonymous)” option.

---

## Configuration
- File types: edit `ALLOWED_EXTS` in `app.py`.
- Time‑series detection: edit `EXPECTED_TIME_SERIES` in `app.py`.
- The app shows up to 2 files; adjust the `multiselect` slice if you want more.

---

## Troubleshooting
- “ModuleNotFoundError: No module named 'gcsfs'/'s3fs'”:
  ```powershell
  pip install gcsfs s3fs
  ```
- “DefaultCredentialsError” on GCS:
  - Upload a Service Account JSON (uncheck Public) or run `gcloud auth application-default login`.
- “Access Denied”:
  - Ensure your identity/service account has `storage.objects.list` and `storage.objects.get` (GCS) or equivalent S3 permissions.
- PowerShell activation blocked:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
  .\.venv\Scripts\Activate
  ```
- Streamlit not found:
  ```powershell
  python -m streamlit run app.py
  ```

---

## Project Structure