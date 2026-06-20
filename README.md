# UAS Analisis Kimia Air Panas Bumi

Project ini dibagikan lewat GitHub tanpa folder virtual environment (`.venv`).
Folder `.venv` memang sebaiknya tidak di-push karena ukurannya besar, bergantung
sistem operasi, dan sering rusak saat dipakai di komputer lain.

## Cara pakai paling cepat

### Linux / macOS

```bash
bash scripts/setup.sh
bash scripts/run_app.sh
```

### Windows

Jalankan perintah berikut di PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run src/app.py
```

## Isi repo yang penting

- `src/app.py` untuk dashboard Streamlit
- `src/pipeline.py` untuk menjalankan analisis dari terminal
- `requirements.txt` untuk daftar dependency
- `data/raw/` untuk data mentah
- `data/processed/` untuk hasil CSV analisis
- `outputs/figures/` untuk grafik PNG hasil analisis
- `outputs/reports/` untuk ringkasan run

## Catatan

- `.venv/` tidak ikut GitHub, tetapi bisa dibuat ulang dengan `requirements.txt`
- input default diatur di `config/analysis_config.yaml`
- dashboard dapat memakai data bawaan atau unggahan Excel/CSV; hasilnya dapat diunduh dari tab `Unduh Hasil`
- untuk menjalankan lewat terminal: `bash scripts/run_pipeline.sh`
- jika ingin menjalankan test:

```bash
./.venv/bin/pytest
```
