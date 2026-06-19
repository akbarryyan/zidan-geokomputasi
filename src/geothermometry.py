"""
Geotermometer kimia air panas bumi — semua formula dari Powell & Cumming (2010).

Estimasi suhu reservoir menggunakan konsentrasi SiO2, Na, K, Ca, dan Mg.
Semua hasil bersifat indikatif — bukan kesimpulan geologi definitif.

Referensi utama:
    Powell & Cumming (2010) Stanford Geothermal Workshop Spreadsheet
    Fournier (1977, 1979), Truesdell (1976), Giggenbach (1988),
    Tonani (1980), Nieva & Nieva (1987), Arnorsson et al. (1983),
    Fournier & Truesdell (1973)
"""

import logging
import math

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Batas validitas setiap geotermometer (°C)
VALIDITY_RANGES: dict[str, tuple[float, float]] = {
    "quartz_conductive":    (20,  250),
    "quartz_adiabatic":     (20,  250),
    "alpha_cristobalite":   (20,  120),
    "beta_cristobalite":    (20,  120),
    "amorphous_silica":     (0,   100),
    "chalcedony":           (25,  180),
    "nk_fournier1979":      (180, 350),
    "nk_truesdell1976":     (100, 300),
    "nk_tonani1980":        (100, 350),
    "nk_giggenbach1988":    (100, 350),
    "nk_nieva1987":         (100, 350),
    "nk_arnorsson1983":     (25,  250),
    "nkca_fournier1973":    (0,   350),
    "kmg_giggenbach1986":   (25,  210),
}


def _safe_log10(value) -> float | None:
    """Kembalikan log10 atau None jika nilai tidak valid."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or f <= 0:
        return None
    return math.log10(f)


def _check_inputs(*args) -> bool:
    """True jika semua argumen adalah float positif yang valid."""
    for v in args:
        if v is None:
            return False
        try:
            f = float(v)
        except (TypeError, ValueError):
            return False
        if math.isnan(f) or f <= 0:
            return False
    return True


# ── Geotermometer SiO₂ ──────────────────────────────────────────────────────

def quartz_geothermometer(sio2_mg_per_kg) -> float | None:
    """
    Geotermometer kuarsa konduktif (Fournier 1977).

    T(°C) = 1309 / (5.19 - log₁₀[SiO₂]) - 273.15
    Berlaku > 150°C (tanpa kehilangan steam).
    """
    log_s = _safe_log10(sio2_mg_per_kg)
    if log_s is None:
        return None
    denom = 5.19 - log_s
    return round(1309 / denom - 273.15, 1) if denom > 0 else None


def quartz_adiabatic(sio2_mg_per_kg) -> float | None:
    """
    Geotermometer kuarsa adiabatik (Fournier 1977).

    T(°C) = 1522 / (5.75 - log₁₀[SiO₂]) - 273.15
    Untuk fluida yang kehilangan steam secara adiabatik sebelum sampling.
    """
    log_s = _safe_log10(sio2_mg_per_kg)
    if log_s is None:
        return None
    denom = 5.75 - log_s
    return round(1522 / denom - 273.15, 1) if denom > 0 else None


def chalcedony_geothermometer(sio2_mg_per_kg) -> float | None:
    """
    Geotermometer kalsedoni (Fournier 1977).

    T(°C) = 1032 / (4.69 - log₁₀[SiO₂]) - 273.15
    Berlaku 25–180°C.
    """
    log_s = _safe_log10(sio2_mg_per_kg)
    if log_s is None:
        return None
    denom = 4.69 - log_s
    return round(1032 / denom - 273.15, 1) if denom > 0 else None


def alpha_cristobalite(sio2_mg_per_kg) -> float | None:
    """
    Geotermometer α-kristobalit (Fournier 1977).

    T(°C) = 1000 / (4.78 - log₁₀[SiO₂]) - 273.15
    Mineral silika stabil < 120°C.
    """
    log_s = _safe_log10(sio2_mg_per_kg)
    if log_s is None:
        return None
    denom = 4.78 - log_s
    return round(1000 / denom - 273.15, 1) if denom > 0 else None


def beta_cristobalite(sio2_mg_per_kg) -> float | None:
    """
    Geotermometer β-kristobalit (Fournier 1977).

    T(°C) = 781 / (4.51 - log₁₀[SiO₂]) - 273.15
    """
    log_s = _safe_log10(sio2_mg_per_kg)
    if log_s is None:
        return None
    denom = 4.51 - log_s
    return round(781 / denom - 273.15, 1) if denom > 0 else None


def amorphous_silica(sio2_mg_per_kg) -> float | None:
    """
    Geotermometer silika amorf (Fournier 1977).

    T(°C) = 731 / (4.52 - log₁₀[SiO₂]) - 273.15
    Batas atas kelarutan silika amorf, indikasi suhu dangkal/rendah.
    """
    log_s = _safe_log10(sio2_mg_per_kg)
    if log_s is None:
        return None
    denom = 4.52 - log_s
    return round(731 / denom - 273.15, 1) if denom > 0 else None


# ── Geotermometer Na/K ───────────────────────────────────────────────────────

def nk_fournier1979(na_mg_per_kg, k_mg_per_kg) -> float | None:
    """
    Geotermometer Na/K Fournier (1979).

    T(°C) = 1217 / (log₁₀(Na/K) + 1.483) - 273.15
    Rasio berat (mg/kg). Berlaku 180–350°C.
    """
    if not _check_inputs(na_mg_per_kg, k_mg_per_kg):
        return None
    log_r = _safe_log10(float(na_mg_per_kg) / float(k_mg_per_kg))
    if log_r is None:
        return None
    denom = log_r + 1.483
    return round(1217 / denom - 273.15, 1) if denom != 0 else None


def nk_truesdell1976(na_mg_per_kg, k_mg_per_kg) -> float | None:
    """
    Geotermometer Na/K Truesdell (1976).

    T(°C) = 855.6 / (log₁₀(Na/K) + 0.857) - 273.15
    Rasio berat (mg/kg). Berlaku 100–300°C.
    """
    if not _check_inputs(na_mg_per_kg, k_mg_per_kg):
        return None
    log_r = _safe_log10(float(na_mg_per_kg) / float(k_mg_per_kg))
    if log_r is None:
        return None
    denom = log_r + 0.857
    return round(855.6 / denom - 273.15, 1) if denom != 0 else None


def nk_tonani1980(na_mg_per_kg, k_mg_per_kg) -> float | None:
    """
    Geotermometer Na/K Tonani (1980).

    T(°C) = 883 / (log₁₀(Na/K) + 0.780) - 273.15
    Rasio berat (mg/kg).
    """
    if not _check_inputs(na_mg_per_kg, k_mg_per_kg):
        return None
    log_r = _safe_log10(float(na_mg_per_kg) / float(k_mg_per_kg))
    if log_r is None:
        return None
    denom = log_r + 0.780
    return round(883 / denom - 273.15, 1) if denom != 0 else None


def nk_giggenbach1988(na_mg_per_kg, k_mg_per_kg) -> float | None:
    """
    Geotermometer Na/K Giggenbach (1988).

    T(°C) = 1390 / (1.75 + log₁₀(Na_mol/K_mol)) - 273.15
    Menggunakan rasio MOLAR: Na_mol = Na/22.99, K_mol = K/39.10.
    Berlaku 100–350°C.
    """
    if not _check_inputs(na_mg_per_kg, k_mg_per_kg):
        return None
    na_mol = float(na_mg_per_kg) / 22.99
    k_mol  = float(k_mg_per_kg)  / 39.10
    log_r  = _safe_log10(na_mol / k_mol)
    if log_r is None:
        return None
    denom = 1.75 + log_r
    return round(1390 / denom - 273.15, 1) if denom != 0 else None


def nk_nieva1987(na_mg_per_kg, k_mg_per_kg) -> float | None:
    """
    Geotermometer Na/K Nieva & Nieva (1987).

    T(°C) = 1179 / (log₁₀(Na/K) + 1.470) - 273.15
    Rasio berat (mg/kg). Dikalibrasi untuk sistem geothermal Meksiko.
    """
    if not _check_inputs(na_mg_per_kg, k_mg_per_kg):
        return None
    log_r = _safe_log10(float(na_mg_per_kg) / float(k_mg_per_kg))
    if log_r is None:
        return None
    denom = log_r + 1.470
    return round(1179 / denom - 273.15, 1) if denom != 0 else None


def nk_arnorsson1983(na_mg_per_kg, k_mg_per_kg) -> float | None:
    """
    Geotermometer Na/K Arnorsson et al. (1983).

    T(°C) = 1319 / (log₁₀(Na/K) + 1.699) - 273.15
    Rasio berat (mg/kg). Dikalibrasi dari sistem geothermal Islandia.
    Berlaku 25–250°C.
    """
    if not _check_inputs(na_mg_per_kg, k_mg_per_kg):
        return None
    log_r = _safe_log10(float(na_mg_per_kg) / float(k_mg_per_kg))
    if log_r is None:
        return None
    denom = log_r + 1.699
    return round(1319 / denom - 273.15, 1) if denom != 0 else None


# ── Geotermometer Na-K-Ca ────────────────────────────────────────────────────

def nkca_fournier1973(
    na_mg_per_kg,
    k_mg_per_kg,
    ca_mg_per_kg,
) -> float | None:
    """
    Geotermometer Na-K-Ca Fournier & Truesdell (1973).

    T(°C) = 1647 / (log₁₀(Na/K) + β × (log₁₀(√Ca/Na) + 2.06) + 2.47) - 273.15

    β = 4/3 jika log₁₀(√Ca/Na) + 2.06 > 0  (air Ca-kaya, suhu < 100°C)
    β = 1/3 jika log₁₀(√Ca/Na) + 2.06 ≤ 0  (air Na-kaya, suhu > 100°C)

    Catatan: Tanpa koreksi Mg (versi sederhana).
    Semua konsentrasi dalam mg/kg (rasio berat).
    """
    if not _check_inputs(na_mg_per_kg, k_mg_per_kg, ca_mg_per_kg):
        return None
    na = float(na_mg_per_kg)
    k  = float(k_mg_per_kg)
    ca = float(ca_mg_per_kg)

    log_nk = _safe_log10(na / k)
    if log_nk is None:
        return None

    sqrt_ca = math.sqrt(ca)
    log_sqca_na = _safe_log10(sqrt_ca / na)
    if log_sqca_na is None:
        return None

    term = log_sqca_na + 2.06
    beta = 4/3 if term > 0 else 1/3
    denom = log_nk + beta * term + 2.47
    return round(1647 / denom - 273.15, 1) if denom != 0 else None


# ── Geotermometer K/Mg ───────────────────────────────────────────────────────

def kmg_giggenbach1986(k_mg_per_kg, mg_mg_per_kg) -> float | None:
    """
    Geotermometer K/Mg Giggenbach (1986, diterbitkan 1988).

    T(°C) = 4410 / (14.0 - log₁₀(K²_mol / Mg_mol)) - 273.15
    Berlaku 25–210°C. Sensitif terhadap pendinginan konduksi.
    """
    if not _check_inputs(k_mg_per_kg, mg_mg_per_kg):
        return None
    k_mol  = float(k_mg_per_kg)  / 39.10
    mg_mol = float(mg_mg_per_kg) / 24.31
    ratio  = (k_mol ** 2) / mg_mol
    log_r  = _safe_log10(ratio)
    if log_r is None:
        return None
    denom = 14.0 - log_r
    return round(4410 / denom - 273.15, 1) if denom != 0 else None


# Alias backward-compat (nama lama dipakai di geothermometer_summary plot)
kmg_giggenbach1988 = kmg_giggenbach1986


# ── Fungsi utama ─────────────────────────────────────────────────────────────

def calculate_geothermometers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Terapkan semua 14 geotermometer Powell (2010) ke seluruh dataset.

    Kolom input yang dibutuhkan: sample_id, sio2, na, k, ca, mg.
    Kolom dengan nilai kosong / tidak valid menghasilkan NaN.

    Returns
    -------
    pd.DataFrame dengan kolom:
        sample_id, sample_name (jika ada),
        — SiO₂ —
        t_quartz_°C, t_quartz_adiabatic_°C,
        t_chalcedony_°C, t_alpha_cristobalite_°C,
        t_beta_cristobalite_°C, t_amorphous_silica_°C,
        — Na/K —
        t_nk_fournier1979_°C, t_nk_truesdell1976_°C,
        t_nk_tonani1980_°C, t_nk_giggenbach1988_°C,
        t_nk_nieva1987_°C, t_nk_arnorsson1983_°C,
        — Na-K-Ca —
        t_nkca_fournier1973_°C,
        — K/Mg —
        t_kmg_giggenbach1986_°C
    """
    rows = []

    for idx in df.index:
        def get(col):
            return df.at[idx, col] if col in df.columns else np.nan

        sid  = get("sample_id")
        name = get("sample_name") if "sample_name" in df.columns else ""

        sio2 = get("sio2")
        na   = get("na")
        k    = get("k")
        ca   = get("ca")
        mg   = get("mg")

        rows.append({
            "sample_id":   sid,
            "sample_name": name,
            # SiO₂
            "t_quartz_°C":            quartz_geothermometer(sio2),
            "t_quartz_adiabatic_°C":  quartz_adiabatic(sio2),
            "t_chalcedony_°C":        chalcedony_geothermometer(sio2),
            "t_alpha_cristobalite_°C":alpha_cristobalite(sio2),
            "t_beta_cristobalite_°C": beta_cristobalite(sio2),
            "t_amorphous_silica_°C":  amorphous_silica(sio2),
            # Na/K
            "t_nk_fournier1979_°C":   nk_fournier1979(na, k),
            "t_nk_truesdell1976_°C":  nk_truesdell1976(na, k),
            "t_nk_tonani1980_°C":     nk_tonani1980(na, k),
            "t_nk_giggenbach1988_°C": nk_giggenbach1988(na, k),
            "t_nk_nieva1987_°C":      nk_nieva1987(na, k),
            "t_nk_arnorsson1983_°C":  nk_arnorsson1983(na, k),
            # Na-K-Ca
            "t_nkca_fournier1973_°C": nkca_fournier1973(na, k, ca),
            # K/Mg
            "t_kmg_giggenbach1986_°C":kmg_giggenbach1986(k, mg),
        })

    result = pd.DataFrame(rows)
    logger.info(f"14 geotermometer dihitung untuk {len(result)} sampel.")
    return result
