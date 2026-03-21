## DESCRIPTION

*i.hyper.geology* performs geological rock family classification,
mineralogical range assessment, and weathering grade mapping from
hyperspectral imagery imported as 3D raster maps (`raster_3d`) by
[i.hyper.import](i.hyper.import.html).

The module reads wavelength metadata from hyperspectral 3D raster bands
and computes up to 15 spectral indicators from VNIR (400-1000 nm) and
SWIR (1000-2500 nm) diagnostic absorption features. These indicators
drive three expert-system classifications: rock family (8 classes),
weathering grade (W0-W5), and hydrothermal/supergene alteration type
(10 categories).

*i.hyper.geology* is part of the **i.hyper** module family designed for
hyperspectral data import, processing, and analysis in GRASS. It
provides a geologically interpretable output suite for mineral exploration,
mine-site mapping, lithological survey, and environmental monitoring of
acid mine drainage (AMD).

### Rock family classification

Eight rock families plus an uncertain class are mapped:

| Class | Label | Key diagnostic features |
|-------|-------|------------------------|
| 0 | Masked | NDVI > 0.3 (vegetation) |
| 1 | Mafic | Fe2+ ~1000 nm, Mg-OH 2320 nm (chlorite), Fe-oxide VNIR |
| 2 | Ultramafic | Strong Mg-OH 2315-2325 nm, Fe2+ 900/1050 nm, absent Al-OH |
| 3 | Felsic | Al-OH dominant 2195-2220 nm, alunite/kaolinite possible |
| 4 | Intermediate | Mixed Fe2+ + Al-OH + Mg-OH (hornblende) |
| 5 | Carbonate sedimentary | CO3 absorption 2340 nm (calcite) / 2320 nm (dolomite) |
| 6 | Siliciclastic sedimentary | Clay Al-OH 2200-2220 nm, Fe-oxide staining |
| 7 | Metamorphic | Mica + chlorite + amphibole, low Fe-oxide |
| 8 | Evaporite/Sulphate | Gypsum 1750 nm, alunite 2270 nm, jarosite VNIR |
| 9 | Uncertain/Mixed | No dominant class above minimum score threshold |

### Weathering grade

Six ISRM-inspired weathering grades are assessed spectroscopically:

| Grade | Label | Spectral signature |
|-------|-------|--------------------|
| W0 | Fresh | Primary minerals dominant, Fe2+ intact, no clay/oxide coatings |
| W1 | Slightly weathered | Minor Fe-oxide staining, primary minerals still dominant |
| W2 | Moderately weathered | Strengthening Fe-oxide, incipient kaolinite/chlorite |
| W3 | Highly weathered | Strong Fe-oxide, clay minerals dominant |
| W4 | Completely weathered | Very strong Fe-oxide (laterite), clay-dominant spectrum |
| W5 | Residual soil | Deep laterite/bauxite profile, goethite/hematite at maximum |

### Alteration type

Ten hydrothermal and supergene alteration categories support mining and
exploration applications:

| Code | Type | Key minerals |
|------|------|-------------|
| 1 | Unaltered | Primary mineralogy, all indicators low |
| 2 | Propylitic | Chlorite + calcite + epidote |
| 3 | Phyllic | White mica (sericite/muscovite) 2195-2210 nm |
| 4 | Argillic | Kaolinite 2165/2205 nm |
| 5 | Advanced argillic | Alunite + dickite/pyrophyllite |
| 6 | Supergene | Secondary goethite/hematite, low jarosite |
| 7 | AMD active | Jarosite + efflorescent sulphates |
| 8 | AMD mature | Hydrated goethite/schwertmannite |
| 9 | Carbonate alteration | Carbonatization, skarn, calcite veining |
| 10 | Serpentinization | Serpentine + talc + chlorite (ultramafic) |

## NOTES

### Input requirements

The module expects input data to be a 3D raster map created by
*i.hyper.import* or any 3D raster with wavelength metadata stored in
band-level metadata following the *i.hyper* standard format:
**wavelength**, **FWHM**, **valid**, and **unit**.

### Spectral indicators

The module computes 15 spectral indicators via **r.mapcalc**:

**Band depth indicators** (normalized band depth = `1 - rho_c / mean(rho_l, rho_r)`):

- `jarosite_vnir` : depth at 430 nm (400/430/470 nm bands)
- `goethite_900` : depth at 900 nm (750/900/1050 nm)
- `ferrous_1000` : depth at 1000 nm; pyroxene/olivine Fe2+ (850/1000/1200 nm)
- `hydroxyl_1400` : depth at 1400 nm; OH overtone (1350/1400/1500 nm)
- `water_1900` : depth at 1900 nm; H2O combination (1800/1900/2000 nm)
- `gypsum_1750` : depth at 1750 nm; gypsum SO4 feature (1700/1750/1800 nm)
- `aloh_2200` : depth at 2200 nm; Al-OH minerals (2100/2200/2280 nm)
- `alunite_2270` : depth at 2270 nm; alunite SO4 (2220/2270/2310 nm)
- `mgoh_2300` : depth at 2320 nm; Mg-OH minerals (2250/2320/2400 nm)
- `carbonate_2340` : depth at 2340 nm; CO3 (2290/2340/2400 nm)

**Ratio indicators**:

- `hematite_vnir` : rho630/rho490 (hematite doublet, Fe3+)
- `fe_oxide_broad` : rho750/rho550 (broad Fe3+ charge-transfer)
- `aloh_position` : rho2165/rho2220 (>1 = kaolinite direction; <1 = muscovite direction)

**Composite indices** from Tolentino et al. (2025):

- `reactivity_index` : (rho2210 + rho2395) / (rho2285 + rho2330); AMD reactivity range 0.66-2.11
- `clay_mixture_index` : (rho2168 × rho2224) / rho2198; clay mixtures range 1.15-4.34

### Classification method

Rock family classification uses a weighted scoring approach. For each
of the 8 rock families, a score is computed as a weighted linear
combination of relevant spectral indicators. The class with the maximum
score (minimum threshold 0.15) is assigned. When indicator bands are
absent (no band within 25 nm tolerance), the indicator is set to a
neutral constant and does not penalize any class. Vegetation pixels
(NDVI > 0.3) are masked to class 0.

The priority order for tie-breaking when scores are equal is:
Evaporite/Sulphate > Carbonate > Ultramafic > Mafic > Metamorphic >
Felsic > Intermediate > Siliciclastic.

### Band tolerance

The **find_band()** function uses a default tolerance of 25 nm when
searching for the closest band to each diagnostic wavelength. If no band
falls within this window, the indicator is disabled and a warning is
issued. The tolerance ensures robustness to slight wavelength shifts
between sensors (EnMAP ~6.5 nm sampling, PRISMA ~10 nm, DESIS/Tanager
~2-3 nm).

### Flags

The **-n** flag restricts processing to only bands marked as valid
(`valid=1`) in the metadata. This excludes atmospheric water vapour
absorption bands (around 1400 and 1900 nm) if they were flagged during
import.

The **-i** flag prints spectral coverage diagnostics and capability
assessment without processing any raster data. Use this first to
understand what geological information is accessible from a given sensor
dataset.

The **-m** flag outputs all 15 individual spectral indicator maps using
the provided `output_prefix`. These floating-point maps are useful for
threshold tuning, visual inspection, or input to custom classification
workflows.

The **-v** flag prints diagnostic messages listing the exact wavelength
of each band used for each indicator computation. Useful for validating
sensor-to-wavelength matching.

### Output metadata

All output maps receive category labels (via **r.category**) and
descriptive metadata (via **r.support**). Color tables are automatically
assigned: a geological color scheme for the family map, a cold-to-warm
gradient for weathering, and a categorical scheme for alteration.

### Limitations

- Classification accuracy depends strongly on SWIR coverage (1000-2500 nm).
  VNIR-only sensors (e.g., Sentinel-2) will miss critical carbonate,
  clay, and hydroxyl features.
- Spectra must be in surface reflectance units (0-1 range). Top-of-
  atmosphere radiance or DN values will produce invalid results.
- Dense vegetation cover (NDVI > 0.3) is masked; sparse vegetation or
  mixed pixels may still influence results.
- Lithological units with complex mineral mixtures (e.g., migmatites,
  mixed volcanics) may fall into the Uncertain/Mixed class.
- The 25 nm band tolerance may cause incorrect band selection for
  sensors with large spectral gaps (e.g., missing SWIR2 region).

## EXAMPLES

::: code

    # Basic rock family mapping from EnMAP data
    i.hyper.geology input=enmap \
                    output_family=enmap_rock_family

:::

::: code

    # Full geological assessment suite
    i.hyper.geology input=prisma \
                    output_family=prisma_lithology \
                    output_weathering=prisma_weathering \
                    output_alteration=prisma_alteration

:::

::: code

    # Check spectral capabilities before processing
    i.hyper.geology input=tanager \
                    output_family=dummy \
                    -i

    # Console output (example):
    # ============================================================
    # i.hyper.geology - Geological Assessment Capabilities
    # ============================================================
    # Sensor spectral coverage: 400.0 - 2500.0 nm (400 bands)
    #
    # Spectral Region Coverage:
    #   VNIR Fe-oxide (400-1000 nm):   AVAILABLE - 200 bands
    #   NIR Fe2+ (900-1100 nm):         AVAILABLE - 20 bands
    #   SWIR OH/H2O (1350-1450 nm):     AVAILABLE - 8 bands
    #   SWIR H2O (1800-2000 nm):        AVAILABLE - 18 bands
    #   SWIR Al-OH (2100-2300 nm):      AVAILABLE - 36 bands
    #   SWIR Mg-OH (2250-2400 nm):      AVAILABLE - 28 bands
    #   SWIR CO3 (2290-2400 nm):        AVAILABLE - 20 bands

:::

::: code

    # Map only valid bands, export mineral indicator maps
    i.hyper.geology input=enmap \
                    output_family=enmap_lithology \
                    output_weathering=enmap_weathering \
                    output_alteration=enmap_alteration \
                    output_prefix=enmap_minerals \
                    -n -m

    # This produces maps such as:
    #   enmap_minerals_aloh_2200
    #   enmap_minerals_mgoh_2300
    #   enmap_minerals_carbonate_2340
    #   enmap_minerals_goethite_900
    #   enmap_minerals_gypsum_1750
    #   ... (15 total indicator maps)

:::

::: code

    # AMD monitoring workflow for mine site
    # Step 1: Import drone VNIR-SWIR hyperspectral data
    i.hyper.import input=/data/drone_hsi.hdr \
                   product=envi \
                   output=drone_hsi

    # Step 2: Atmospheric correction (if not already corrected)
    # i.hyper.atcorr ...

    # Step 3: Full geological assessment
    i.hyper.geology input=drone_hsi \
                    output_family=drone_lithology \
                    output_weathering=drone_weathering \
                    output_alteration=drone_alteration \
                    output_prefix=drone_minerals \
                    -n -m -v

    # Step 4: Extract AMD-affected areas (alteration class 7 = AMD active)
    r.mapcalc expression="amd_mask = if(drone_alteration == 7, 1, null())"

    # Step 5: Statistics on AMD extent
    r.univar map=amd_mask

    # Step 6: Visualize
    d.rast map=drone_alteration
    d.legend raster=drone_alteration

:::

::: code

    # Bauxite prospectivity mapping using weathering output
    # High weathering grades (W4-W5) in felsic/intermediate rocks
    # are indicative of bauxite formation potential
    i.hyper.geology input=satellite_hsi \
                    output_family=lithology \
                    output_weathering=weathering

    r.mapcalc expression="bauxite_prospective = \
        if((weathering == 4 || weathering == 5) && \
           (lithology == 3 || lithology == 4), 1, null())"

    r.colors map=bauxite_prospective color=bgyr

:::

::: code

    # Limit processing to SWIR range for alteration mapping only
    i.hyper.geology input=enmap \
                    output_family=enmap_family \
                    output_alteration=enmap_alteration \
                    min_wavelength=1000 \
                    max_wavelength=2500

:::

## SEE ALSO

[i.hyper.import](i.hyper.import.html),
[i.hyper.continuum](i.hyper.continuum.html),
[i.hyper.indices](i.hyper.indices.html),
[i.hyper.albedo](i.hyper.albedo.html),
[i.hyper.rgb](i.hyper.rgb.html),
[r.mapcalc](https://grass.osgeo.org/grass-stable/manuals/r.mapcalc.html),
[r.colors](https://grass.osgeo.org/grass-stable/manuals/r.colors.html),
[r.category](https://grass.osgeo.org/grass-stable/manuals/r.category.html),
[r.univar](https://grass.osgeo.org/grass-stable/manuals/r.univar.html),
[r3.info](https://grass.osgeo.org/grass-stable/manuals/r3.info.html)

## REFERENCES

- Koerting, F., et al. (2024). VNIR-SWIR Imaging Spectroscopy for
  Mining: A Review of Methods and Applications. *Mining*, 4, 1013-1057.
  https://doi.org/10.3390/mining4040056
- Tolentino, P.L.M., et al. (2025). Drone-Based VNIR-SWIR Hyperspectral
  Imaging for Acid Mine Drainage Characterisation. *Drones*, 9, 313.
  https://doi.org/10.3390/drones9050313
- Kouzeli, K., et al. (2025). Exploitation of Satellite Imagery for
  Bauxite Mine Waste Characterisation. *ISPRS Archives*, Vol. XLVIII-2/W4.
  https://doi.org/10.5194/isprs-archives-XLVIII-2-W4-2025
- Clark, R.N., et al. (1990). High spectral resolution reflectance
  spectroscopy of minerals. *Journal of Geophysical Research: Solid
  Earth*, 95(B8), 12653-12680.
- Hunt, G.R. (1977). Spectral signatures of particulate minerals in the
  visible and near infrared. *Geophysics*, 42(3), 501-513.
- Kokaly, R.F., et al. (2017). USGS Spectral Library Version 7. U.S.
  Geological Survey Data Series 1035.
  https://doi.org/10.3133/ds1035

## AUTHORS

Created for the i.hyper module family

Based on spectral geology methods from Koerting et al. (2024),
Tolentino et al. (2025), and Kouzeli et al. (2025).
