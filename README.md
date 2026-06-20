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

Sebelum menjalankan analisis, instal LibreOffice agar 14 diagramsheet
Powell-Cumming dapat dirender dari workbook referensi. Pada Ubuntu/Debian:

```bash
sudo apt install libreoffice
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

Instal LibreOffice terlebih dahulu dan pastikan `soffice.exe` tersedia di `PATH`.

## Isi repo yang penting

- `src/app.py` untuk dashboard Streamlit
- `src/pipeline.py` untuk menjalankan analisis dari terminal
- `requirements.txt` untuk daftar dependency
- `docs/data-mentah/Kimia Air_Tugas 1.xlsx` untuk data mentah Kimia Air
- `docs/data-mentah/Tugas 1_Ion Balance.xlsx` untuk data mentah Ion Balance
- `docs/data-referensi/Contoh_liquid_analysis_v3_powell-cumming_2010_stanfordgw.xlsx` sebagai template Input dan referensi metode Powell-Cumming
- `data/processed/` untuk hasil CSV analisis
- `outputs/figures/` untuk grafik PNG hasil analisis
- `outputs/reports/` untuk ringkasan run

## Catatan

- `.venv/` tidak ikut GitHub, tetapi bisa dibuat ulang dengan `requirements.txt`
- LibreOffice wajib terpasang dan tersedia sebagai perintah `libreoffice` atau `soffice` untuk merender diagramsheet Powell-Cumming secara identik
- input default diatur di `config/analysis_config.yaml`
- dashboard menyajikan dataset Kimia Air dan Ion Balance secara terpisah
- sheet `Input` pada workbook Stanford adalah template untuk memasukkan data mentah, bukan sumber sampel tambahan
- dashboard dapat memakai data bawaan atau unggahan Excel/CSV; hasilnya dapat diunduh dari tab `Unduh Hasil`
- untuk menjalankan lewat terminal: `bash scripts/run_pipeline.sh`
- jika ingin menjalankan test:

```bash
./.venv/bin/pytest
```
