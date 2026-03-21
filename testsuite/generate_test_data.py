#!/usr/bin/env python3
"""
Generate synthetic hyperspectral geological test data for i.hyper.geology.

Author:    Yann Chemin <yann.chemin@gmail.com>
Copyright: (C) 2026 by Yann Chemin and the GRASS Development Team
License:   GPL-2.0-or-later

Creates synthetic spectral scenes representative of six geological end-members
covering the VNIR-SWIR range (400-2500 nm) with 43 diagnostic bands.  Each
scene is a 20x20 pixel 2D raster per band, named <scene>#<band_num>, plus an
accompanying 3D raster created via r3.mapcalc for raster3d_info() queries.

Spectral scenes available
--------------------------
fresh_mafic      Basalt/gabbro - strong Fe2+ at 1000 nm, weak SWIR
goethite         Highly weathered mafic - broad 900 nm Fe3+ absorption
kaolinite        Argillic-altered felsic - deep Al-OH at 2200 nm (kaolinite pos)
white_mica       Phyllic-altered felsic - Al-OH at 2200 nm (muscovite pos)
carbonate        Limestone - deep CO3 absorption at 2340 nm
gypsum_amd       Evaporite/AMD - gypsum 1750 nm + jarosite VNIR
serpentinite     Ultramafic - strong Mg-OH at 2320 nm, no Al-OH

Usage (inside a GRASS session)
-------------------------------
    python3 generate_test_data.py [--scene all|<name>] [--cleanup]
"""

import argparse
import os
import sys

try:
    import grass.script as gs
except ImportError:
    print("Error: must be run inside a GRASS GIS session.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Spectral band definitions
# 43 bands selected to cover all diagnostic wavelengths used by i.hyper.geology
# ---------------------------------------------------------------------------

BAND_WAVELENGTHS = [
    400, 420, 430, 450, 470, 490, 510, 530, 550, 580,
    620, 650, 680, 700, 730, 750, 800, 850, 900, 950,
    1000, 1050, 1100, 1200, 1350, 1400, 1450, 1500,
    1580, 1650, 1700, 1750, 1800, 1900, 2000, 2100,
    2165, 2198, 2200, 2220, 2250, 2270, 2285, 2290,
    2310, 2320, 2330, 2340, 2390, 2395, 2400, 2450, 2500,
]
N_BANDS = len(BAND_WAVELENGTHS)

FWHM_NM = 10.0  # All bands use 10 nm FWHM for simplicity


# ---------------------------------------------------------------------------
# Spectral end-member reflectance functions
# Each returns a reflectance value in [0, 1] for a given wavelength (nm).
# Values are per-pixel constants; spatial variability is added as ±5% noise.
# ---------------------------------------------------------------------------

def _fresh_mafic(wl):
    """Basalt/gabbro: Fe2+ doublet at 1000-1050 nm, weak SWIR."""
    if wl < 500:
        return 0.06
    elif wl < 700:
        return 0.07 + 0.04 * (wl - 500) / 200
    elif wl < 850:
        return 0.11 + 0.04 * (wl - 700) / 150    # rising toward 1000 nm
    elif wl < 1000:
        return 0.15 - 0.06 * (wl - 850) / 150    # Fe2+ absorption shoulder
    elif wl < 1100:
        return 0.09 + 0.06 * (wl - 1000) / 100   # Fe2+ doublet trough
    elif wl < 1400:
        return 0.15
    elif wl < 1450:
        return 0.13    # OH at 1400
    elif wl < 1800:
        return 0.14
    elif wl < 2000:
        return 0.12    # H2O 1900 nm
    else:
        return 0.13


def _goethite(wl):
    """Highly weathered: broad Fe3+ absorption at 900 nm, hematite VNIR."""
    if wl < 450:
        return 0.04   # strong charge-transfer absorption
    elif wl < 550:
        return 0.04 + 0.04 * (wl - 450) / 100
    elif wl < 620:
        return 0.08   # hematite shoulder
    elif wl < 680:
        return 0.10   # hematite doublet ~630 nm peak
    elif wl < 800:
        return 0.12 - 0.06 * (wl - 680) / 120   # drop to 900 nm trough
    elif wl < 950:
        return 0.06   # goethite broad trough
    elif wl < 1100:
        return 0.08 + 0.06 * (wl - 950) / 150
    elif wl < 2100:
        return 0.14
    else:
        return 0.14   # weak SWIR (all indicators near zero)


def _kaolinite(wl):
    """Argillic alteration: Al-OH doublet at 2165/2205 nm (kaolinite).

    Doublet design so that aloh_2200 indicator (center=2200, left=2100, right=2280)
    detects the absorption, and aloh_position ratio (rho2165/rho2220) < 1.0 (kaolinite).
    """
    if wl < 700:
        return 0.20 + 0.05 * (wl - 400) / 300
    elif wl < 1400:
        return 0.25
    elif wl < 1450:
        return 0.18   # OH 1400 nm
    elif wl < 1700:
        return 0.24
    elif wl < 1800:
        return 0.23
    elif wl < 2000:
        return 0.18   # H2O 1900 nm
    elif wl < 2150:
        return 0.24
    elif wl < 2170:
        return 0.08   # first doublet minimum at ~2165 nm (deep)
    elif wl < 2195:
        return 0.18   # recovery between doublet features
    elif wl < 2215:
        return 0.10   # second doublet minimum (covers 2198, 2200 nm bands)
    elif wl < 2280:
        return 0.22   # recovery (covers 2220 nm: rho2220=0.22 > rho2165=0.08 → ratio<1)
    else:
        return 0.22


def _white_mica(wl):
    """Phyllic alteration: Al-OH at 2200-2210 nm (muscovite/sericite)."""
    if wl < 700:
        return 0.22 + 0.06 * (wl - 400) / 300
    elif wl < 1400:
        return 0.28
    elif wl < 1450:
        return 0.20   # OH 1400 nm
    elif wl < 1700:
        return 0.27
    elif wl < 2000:
        return 0.22   # H2O 1900 nm shoulder
    elif wl < 2195:
        return 0.26   # pre-minimum plateau (covers 2150, 2165 nm)
    elif wl < 2230:
        return 0.08   # muscovite minimum covers 2198, 2200, 2220 nm bands
    elif wl < 2280:
        return 0.24   # recovery
    else:
        return 0.24


def _carbonate(wl):
    """Limestone: CO3 absorption at 2340 nm (calcite)."""
    if wl < 700:
        return 0.30 + 0.06 * (wl - 400) / 300
    elif wl < 1400:
        return 0.36
    elif wl < 1450:
        return 0.28   # very slight OH
    elif wl < 2000:
        return 0.34
    elif wl < 2100:
        return 0.34
    elif wl < 2290:
        return 0.35
    elif wl < 2320:
        return 0.35
    elif wl < 2340:
        return 0.35 - 0.18 * (wl - 2320) / 20   # approaching calcite minimum
    elif wl < 2360:
        return 0.17 + 0.18 * (wl - 2340) / 20   # recovery after minimum
    else:
        return 0.35


def _gypsum_amd(wl):
    """AMD evaporite: jarosite VNIR + gypsum 1750 nm + alunite 2270 nm."""
    if wl < 420:
        return 0.05   # jarosite charge-transfer
    elif wl < 450:
        return 0.05   # jarosite absorption trough at 430 nm
    elif wl < 500:
        return 0.10 + 0.10 * (wl - 450) / 50
    elif wl < 700:
        return 0.20
    elif wl < 850:
        return 0.25
    elif wl < 950:
        return 0.15   # jarosite broad 900 nm absorption
    elif wl < 1100:
        return 0.25
    elif wl < 1700:
        return 0.30
    elif wl < 1750:
        return 0.30 - 0.12 * (wl - 1700) / 50   # gypsum 1750 nm feature
    elif wl < 1800:
        return 0.18 + 0.12 * (wl - 1750) / 50
    elif wl < 2000:
        return 0.28
    elif wl < 2100:
        return 0.28
    elif wl < 2150:
        return 0.28
    elif wl < 2200:
        return 0.20   # Al-OH / sulphate 2200 nm
    elif wl < 2250:
        return 0.26
    elif wl < 2270:
        return 0.14   # alunite minimum at 2270 nm
    elif wl < 2310:
        return 0.26
    else:
        return 0.26


def _serpentinite(wl):
    """Ultramafic: strong Mg-OH at 2320 nm, Fe2+ olivine at 900 nm."""
    if wl < 500:
        return 0.08
    elif wl < 700:
        return 0.10 + 0.04 * (wl - 500) / 200
    elif wl < 900:
        return 0.14
    elif wl < 950:
        return 0.09   # olivine/serpentine Fe2+ at 900-950 nm
    elif wl < 1100:
        return 0.14
    elif wl < 1400:
        return 0.16
    elif wl < 1450:
        return 0.12   # OH
    elif wl < 1700:
        return 0.15
    elif wl < 2000:
        return 0.13
    elif wl < 2100:
        return 0.15
    elif wl < 2250:
        return 0.15   # NO Al-OH
    elif wl < 2310:
        return 0.15
    elif wl < 2320:
        return 0.15 - 0.10 * (wl - 2310) / 10   # Mg-OH onset
    elif wl < 2330:
        return 0.05   # serpentine Mg-OH minimum at 2315-2325 nm
    elif wl < 2350:
        return 0.05 + 0.10 * (wl - 2330) / 20
    else:
        return 0.15


SCENE_FUNCTIONS = {
    "fresh_mafic":   _fresh_mafic,
    "goethite":      _goethite,
    "kaolinite":     _kaolinite,
    "white_mica":    _white_mica,
    "carbonate":     _carbonate,
    "gypsum_amd":    _gypsum_amd,
    "serpentinite":  _serpentinite,
}

# Expected dominant outputs for each scene (for assertion helpers)
SCENE_EXPECTATIONS = {
    "fresh_mafic": {
        "family_class": 1,          # Mafic
        "weathering_max": 1,        # W0 or W1
        "alteration_class": 1,      # Unaltered
    },
    "goethite": {
        "family_class_options": [1, 6],  # Mafic or Siliciclastic
        "weathering_min": 2,        # W2 or higher
        "alteration_class_options": [6, 8],  # Supergene or AMD mature
    },
    "kaolinite": {
        "family_class_options": [3, 6],  # Felsic or Siliciclastic
        "alteration_class": 4,      # Argillic
    },
    "white_mica": {
        "family_class": 3,          # Felsic
        "alteration_class": 3,      # Phyllic
    },
    "carbonate": {
        "family_class": 5,          # Carbonate
        "alteration_class_options": [1, 9],  # Unaltered or Carbonate alteration
    },
    "gypsum_amd": {
        "family_class": 8,          # Evaporite
        "alteration_class": 7,      # AMD active
    },
    "serpentinite": {
        "family_class": 2,          # Ultramafic
        "alteration_class": 10,     # Serpentinization
    },
}


# ---------------------------------------------------------------------------
# Data generation helpers
# ---------------------------------------------------------------------------

def _noise_expr(base, noise_frac=0.05):
    """Return an r.mapcalc expression for a spatially noisy constant.

    Adds ±noise_frac * base as a sinusoidal spatial pattern (deterministic,
    reproducible, no random seed needed in tests).
    """
    amp = base * noise_frac
    return f"{base:.6f} + {amp:.6f} * sin(row()) * cos(col())"


def inject_band_metadata(map_name, wavelength_nm, fwhm_nm=10.0,
                          valid=1, unit="nm"):
    """Write wavelength metadata to a 2D raster map via r.support.

    The metadata is stored as structured lines in the map description so that
    i.hyper.geology's parse_wavelength_from_metadata() can read them.

    Format written (one key=value per line):
        wavelength=<value>
        FWHM=<value>
        valid=<0|1>
        unit=<nm|um>
    """
    description = (
        f"wavelength={wavelength_nm:.4f}\n"
        f"FWHM={fwhm_nm:.4f}\n"
        f"valid={int(valid)}\n"
        f"unit={unit}"
    )
    try:
        gs.run_command(
            "r.support",
            map=map_name,
            description=description,
            history=description,
            quiet=True,
        )
    except Exception as exc:
        gs.warning(f"Could not set metadata for {map_name}: {exc}")


def create_scene_bands(scene_name, spectral_fn, region_rows=20, region_cols=20):
    """Create one 2D raster per band for the given scene.

    Band maps are named  <scene_name>#<band_num>  (1-based).
    Returns the list of map names created.
    """
    created = []
    for idx, wl in enumerate(BAND_WAVELENGTHS, start=1):
        map_name = f"{scene_name}#{idx}"
        rho = max(0.001, min(0.999, spectral_fn(wl)))
        # Map name must be quoted in r.mapcalc because '#' is a special operator
        expr = f'"{map_name}" = {_noise_expr(rho)}'
        gs.run_command("r.mapcalc", expression=expr, overwrite=True, quiet=True)
        inject_band_metadata(map_name, wavelength_nm=wl, fwhm_nm=FWHM_NM)
        created.append(map_name)
    return created


def create_scene_3d(scene_name):
    """Create a companion 3D raster named *scene_name* for raster3d_info() calls.

    The depth count (N_BANDS) is what the module reads via gs.raster3d_info().
    Actual band pixel data is read from the individual 2D '#{n}' rasters created
    by create_scene_bands(), so the 3D voxel values are irrelevant.
    """
    gs.run_command(
        "r3.mapcalc",
        expression=f"{scene_name} = 0.10 + 0.001 * z()",
        overwrite=True,
        quiet=True,
    )
    return scene_name


def create_scene(scene_name, spectral_name=None):
    """Create a complete test scene (2D band stack + 3D companion).

    Args:
        scene_name:    GRASS map name prefix used for the band rasters.
        spectral_name: Key in SCENE_FUNCTIONS for the spectral end-member to
                       use.  Defaults to ``scene_name`` when omitted (so that
                       ``create_scene("fresh_mafic")`` still works as before).

    Returns dict with keys:
        'bands_3d'   : name of the 3D raster (for use as module 'input=')
        'band_maps'  : list of 2D band map names
        'n_bands'    : number of bands
        'wavelengths': list of wavelengths
    """
    key = spectral_name if spectral_name is not None else scene_name
    if key not in SCENE_FUNCTIONS:
        raise ValueError(
            f"Unknown spectral name '{key}'. "
            f"Available: {', '.join(SCENE_FUNCTIONS)}"
        )
    spectral_fn = SCENE_FUNCTIONS[key]
    band_maps = create_scene_bands(scene_name, spectral_fn)
    create_scene_3d(scene_name)
    return {
        "bands_3d": scene_name,
        "band_maps": band_maps,
        "n_bands": N_BANDS,
        "wavelengths": BAND_WAVELENGTHS,
    }


def cleanup_scene(scene_name):
    """Remove all raster maps associated with a scene."""
    maps_2d = [f"{scene_name}#{i}" for i in range(1, N_BANDS + 1)]
    # Remove 2D bands
    for m in maps_2d:
        try:
            gs.run_command("g.remove", type="raster", name=m, flags="f", quiet=True)
        except Exception:
            pass
    # Remove 3D companion (named scene_name, not scene_name_3d)
    try:
        gs.run_command("g.remove", type="raster_3d", name=scene_name, flags="f", quiet=True)
    except Exception:
        pass


def setup_test_region(rows=20, cols=20, n_depths=None):
    """Set GRASS region appropriate for geology tests.

    Sets both 2D resolution (res=1) and 3D resolution (res3=1) so that
    r3.mapcalc produces a proper rows x cols x n_depths voxel grid.
    """
    if n_depths is None:
        n_depths = N_BANDS
    gs.run_command(
        "g.region",
        n=rows, s=0, e=cols, w=0,
        res=1, res3=1,
        t=n_depths, b=0, tbres=1,
        quiet=True,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic geological test data for i.hyper.geology"
    )
    parser.add_argument(
        "--scene",
        default="all",
        choices=list(SCENE_FUNCTIONS) + ["all"],
        help="Scene to generate (default: all)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove previously generated test data",
    )
    args = parser.parse_args()

    setup_test_region()

    scenes = list(SCENE_FUNCTIONS) if args.scene == "all" else [args.scene]

    if args.cleanup:
        for sc in scenes:
            print(f"Cleaning up scene: {sc}")
            cleanup_scene(sc)
        print("Done.")
        return

    for sc in scenes:
        print(f"Creating scene: {sc} ({N_BANDS} bands) ...", end=" ", flush=True)
        info = create_scene(sc)
        print(f"OK  ({info['bands_3d']})")

    print(f"\nAll scenes created. Wavelength range: "
          f"{BAND_WAVELENGTHS[0]}-{BAND_WAVELENGTHS[-1]} nm, "
          f"{N_BANDS} bands.")


if __name__ == "__main__":
    main()
