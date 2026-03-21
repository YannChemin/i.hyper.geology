# i.hyper.geology

**GRASS GIS module — Geological rock family classification, mineralogical
range assessment, and weathering grade mapping from hyperspectral imagery**

Part of the [i.hyper](../README.md) module family for VNIR-SWIR hyperspectral
data processing in GRASS GIS.

---

## Overview

`i.hyper.geology` performs spectroscopy-based geological mapping directly
from at-surface reflectance hyperspectral cubes (3D raster maps produced by
`i.hyper.import`).  The module computes up to 15 diagnostic spectral
indicators spanning the VNIR (400–1000 nm) and SWIR (1000–2500 nm) domains,
then applies a weighted, priority-ordered expert classifier to produce three
complementary output maps:

| Output | Content | Classes |
|--------|---------|---------|
| Rock family | Lithological family at surface | 9 classes (0–9) |
| Weathering grade | Degree of chemical weathering | W0–W5 (integer 0–5) |
| Alteration type | Hydrothermal / supergene / AMD style | 10 classes (1–10) |

An optional set of 15 individual mineral indicator maps can be exported with
the `-m` flag.

The module is designed for **mining and geohazard applications** within the
[M4Mining](https://www.m4mining.eu) project framework, but applies to any
geological mapping context where VNIR-SWIR reflectance data are available.

---

## Rock family classes

| Class | Label | Key spectral evidence |
|-------|-------|-----------------------|
| 0 | Masked (vegetation/water) | NDVI > 0.3 |
| 1 | Mafic | Fe²⁺ 1000 nm doublet; Mg-OH 2320 nm when altered |
| 2 | Ultramafic | Strong Mg-OH 2315–2325 nm (serpentine/talc); no Al-OH |
| 3 | Felsic | Al-OH dominant 2195–2220 nm (muscovite position) |
| 4 | Intermediate | Mixed Fe²⁺ + Al-OH + hornblende Mg-OH |
| 5 | Carbonate sedimentary | CO₃²⁻ 2340 nm (calcite) or 2320 nm (dolomite) |
| 6 | Siliciclastic sedimentary | Clay Al-OH 2200 nm; Fe-staining VNIR |
| 7 | Metamorphic | Mica + chlorite/amphibole; low Fe-oxide |
| 8 | Evaporite / Sulphate | Gypsum 1750 nm; alunite 2270 nm; jarosite VNIR |
| 9 | Uncertain / Mixed | No class exceeds minimum score threshold |

## Weathering grades

| Grade | Label | Spectral signature |
|-------|-------|--------------------|
| W0 | Fresh | Fe²⁺ > 0.10; no Fe-oxide coating; no clay |
| W1 | Slightly weathered | Incipient Fe-oxide staining; primary minerals intact |
| W2 | Moderately weathered | Goethite > 0.05; incipient kaolinite/chlorite |
| W3 | Highly weathered | Strong Fe-oxide + clay; weak primary minerals |
| W4 | Completely weathered (saprolite) | Very strong Fe-oxide; clay-dominant |
| W5 | Residual soil / laterite | Maximum Fe-oxide + clay; no primary phases |

## Alteration types

| Code | Label | Diagnostic indicators |
|------|-------|-----------------------|
| 1 | Unaltered | All indicators below threshold |
| 2 | Propylitic | Mg-OH 2300 nm (chlorite) + carbonate 2340 nm |
| 3 | Phyllic | Al-OH > 0.06, position → muscovite (≥ 1.0) |
| 4 | Argillic | Al-OH > 0.06, position → kaolinite (< 1.0) |
| 5 | Advanced argillic | Alunite 2270 nm + gypsum 1750 nm |
| 6 | Supergene | Strong goethite + hematite; no jarosite |
| 7 | AMD active | Jarosite VNIR or reactivity index > 1.5 |
| 8 | AMD mature | Hydrated goethite (900 nm + 1900 nm) |
| 9 | Carbonate alteration | CO₃ > 0.06; low Al-OH; low Mg-OH |
| 10 | Serpentinization | Mg-OH > 0.08; no Al-OH |

---

## Spectral indicators

All 15 indicators are computed as normalised band depths
(`1 − ρ_center / mean(ρ_left, ρ_right)`) or reflectance ratios, then used
as inputs to the scoring classifier.

| Indicator | Wavelengths (nm) | Target mineral / feature |
|-----------|-----------------|--------------------------|
| `jarosite_vnir` | 400 / 430 / 470 | Jarosite (AMD) |
| `hematite_vnir` | 630 / 490 ratio | Hematite |
| `goethite_900` | 750 / 900 / 1050 | Goethite |
| `fe_oxide_broad` | 750 / 550 ratio | Broad Fe³⁺ |
| `ferrous_1000` | 850 / 1000 / 1200 | Pyroxene / Olivine |
| `hydroxyl_1400` | 1350 / 1400 / 1500 | OH overtone |
| `water_1900` | 1800 / 1900 / 2000 | H₂O first overtone |
| `gypsum_1750` | 1700 / 1750 / 1800 | Gypsum SO₄²⁻ |
| `aloh_2200` | 2100 / 2200 / 2280 | Al-OH (clays, mica) |
| `aloh_position` | 2165 / 2220 ratio | Al-OH position: > 1.0 → muscovite (phyllic); < 1.0 → kaolinite (argillic) |
| `alunite_2270` | 2220 / 2270 / 2310 | Alunite / advanced argillic |
| `mgoh_2300` | 2250 / 2320 / 2400 | Mg-OH (chlorite, serpentine, talc) |
| `carbonate_2340` | 2290 / 2340 / 2400 | Calcite / dolomite CO₃²⁻ |
| `reactivity_index` | (2210+2395)/(2285+2330) | AMD-reactive sulphate/clay¹ |
| `clay_mixture_index` | (2168×2224)/2198 | Clay-rich mixed surfaces¹ |

¹ Band ratio indices after Tolentino et al. (2025).

---

## Usage

```bash
# Minimal: rock family only
i.hyper.geology input=enmap_reflectance \
                output_family=enmap_rock_family

# Full outputs: rock family + weathering grade + alteration type
i.hyper.geology input=enmap_reflectance \
                output_family=enmap_rock_family \
                output_weathering=enmap_weathering \
                output_alteration=enmap_alteration

# + individual mineral indicator maps
i.hyper.geology input=enmap_reflectance \
                output_family=enmap_rock_family \
                output_weathering=enmap_weathering \
                output_alteration=enmap_alteration \
                output_prefix=enmap_minerals \
                -m

# Check sensor coverage and capabilities before processing
i.hyper.geology input=enmap_reflectance \
                output_family=dummy \
                -i

# Restrict to valid bands only; verbose indicator scoring
i.hyper.geology input=drone_hyspex \
                output_family=hyspex_rock_family \
                output_weathering=hyspex_weathering \
                output_alteration=hyspex_alteration \
                -n -v
```

### Flags

| Flag | Effect |
|------|--------|
| `-n` | Use only bands marked `valid=1` in metadata |
| `-m` | Export individual mineral indicator maps (requires `output_prefix`) |
| `-i` | Info mode — print spectral coverage table and quit without processing |
| `-v` | Verbose — log which bands are matched to each indicator |

---

## Typical workflow

```bash
# 1. Import hyperspectral data
i.hyper.import input=/data/ENMAP_L2A.hdf \
               product=enmap \
               output=enmap

# 2. (Recommended) Apply continuum removal for enhanced feature depth
i.hyper.continuum input=enmap \
                  output=enmap_cr \
                  min_wavelength=400 \
                  max_wavelength=2500

# 3. Geological assessment
i.hyper.geology input=enmap_cr \
                output_family=enmap_geology \
                output_weathering=enmap_weathering \
                output_alteration=enmap_alteration \
                output_prefix=enmap_minerals \
                -m -n

# 4. Visualise
d.rast map=enmap_geology
d.rast map=enmap_weathering
d.legend map=enmap_geology

# 5. Area statistics per class
r.stats -a input=enmap_geology
r.univar map=enmap_minerals_goethite_900 zones=enmap_geology
```

---

## Sensor compatibility

The module degrades gracefully when a sensor does not cover a spectral region.
Missing regions generate a warning and that class of indicators is set to zero
(neutral), so classification still runs on the available evidence.

| Sensor | VNIR Fe-oxide | SWIR Al-OH | SWIR Mg-OH | SWIR CO₃ | Suitable for |
|--------|:---:|:---:|:---:|:---:|-------------|
| HySpex Mjolnir VS-620 (400–2500 nm) | ✓ | ✓ | ✓ | ✓ | Full assessment |
| EnMap (420–2450 nm, 224 bands) | ✓ | ✓ | ✓ | ✓ | Full assessment |
| PRISMA (400–2500 nm, 238 bands) | ✓ | ✓ | ✓ | ✓ | Full assessment |
| Sentinel-2 MSI (443–2190 nm, 12 bands) | ✓ | partial | ✗ | ✗ | Fe-oxide + kaolinite only |
| WV3-SWIR (1195–2365 nm, 8 bands) | ✗ | ✓ | ✓ | ✓ | SWIR minerals only; no AMD |
| EMIT (380–2500 nm, 285 bands) | ✓ | ✓ | ✓ | ✓ | Full assessment |

---

## References

- Koerting, F., et al. (2024). VNIR-SWIR Imaging Spectroscopy for Mining:
  Insights for Hyperspectral Drone Applications. *Mining*, 4, 1013–1057.
  <https://doi.org/10.3390/mining4040057>
- Tolentino, V., et al. (2025). Drone-Based VNIR-SWIR Hyperspectral Imaging
  for Environmental Monitoring of a Uranium Legacy Mine Site. *Drones*, 9, 313.
  <https://doi.org/10.3390/drones9040313>
- Kouzeli, E., et al. (2025). Satellite imagery for bauxite mine waste mapping
  in the frame of the m4mining project. *ISPRS Archives*, XLVIII-M-7-2025,
  113–120. <https://doi.org/10.5194/isprs-archives-XLVIII-M-7-2025-113-2025>
- Clark, R. N., et al. (1990). High spectral resolution reflectance
  spectroscopy of minerals. *Journal of Geophysical Research*, 95(B8),
  12653–12680.
- Hunt, G. R. (1977). Spectral signatures of particulate minerals in the
  visible and near infrared. *Geophysics*, 42(3), 501–513.
- Kokaly, R. F., et al. (2017). USGS Spectral Library Version 7. *USGS
  Data Series* 1035. <https://doi.org/10.3133/ds1035>

## See also

- [i.hyper.import](../i.hyper.import/README.md) — hyperspectral cube import
- [i.hyper.continuum](../i.hyper.continuum/README.md) — continuum removal
- [i.hyper.indices](../i.hyper.indices/README.md) — spectral indices (86+)
- [i.hyper.albedo](../i.hyper.albedo/README.md) — broadband albedo
- [i.hyper.atcorr](../i.hyper.atcorr/README.md) — atmospheric correction
- [i.hyper.smac](../i.hyper.smac/README.md) — SMAC atmospheric correction
- GRASS manual page: [i.hyper.geology.html](i.hyper.geology.html)

## Testsuite

A gunittest-based testsuite is located in `testsuite/`.  It covers 51 test
cases including basic execution, info mode, wavelength filtering, weathering
classification, alteration classification, indicator physics, and parameter
validation.

```bash
# Run from inside an active GRASS session (location with a writable mapset):
cd testsuite
python3 -m unittest test_i_hyper_geology
```

Test data is generated synthetically by `testsuite/generate_test_data.py`
using seven spectral end-member scenes (fresh mafic, goethite-weathered,
kaolinite, white mica, carbonate, gypsum/AMD, serpentinite).

---

## License

GPL-2.0-or-later — see [LICENSE](LICENSE)

## Authors

Created for the i.hyper module family / M4Mining project (2026).
