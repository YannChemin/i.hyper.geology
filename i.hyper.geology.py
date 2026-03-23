#!/usr/bin/env python
##############################################################################
# MODULE:    i.hyper.geology
# AUTHOR(S): Created for hyperspectral geological mapping
# PURPOSE:   Geological rock family classification, mineralogical range
#            assessment, and weathering grade mapping from hyperspectral imagery
# COPYRIGHT: (C) 2026 by the GRASS Development Team
# SPDX-License-Identifier: GPL-2.0-or-later
##############################################################################

# %module
# % description: Geological rock family classification, weathering grade and alteration type mapping from hyperspectral imagery
# % keyword: imagery
# % keyword: hyperspectral
# % keyword: geology
# % keyword: mineralogy
# % keyword: classification
# % keyword: weathering
# % keyword: alteration
# % keyword: VNIR
# % keyword: SWIR
# %end

# %option G_OPT_R3_INPUT
# % key: input
# % required: yes
# % description: Input hyperspectral 3D raster map (from i.hyper.import)
# % guisection: Input
# %end

# %option G_OPT_R_OUTPUT
# % key: output_family
# % required: yes
# % description: Output rock family classification raster map (integer classes 0-9)
# % guisection: Output
# %end

# %option G_OPT_R_OUTPUT
# % key: output_weathering
# % required: no
# % description: Output weathering grade raster map (W0-W5, integer 0-5)
# % guisection: Output
# %end

# %option G_OPT_R_OUTPUT
# % key: output_alteration
# % required: no
# % description: Output alteration type raster map (integer 1-10)
# % guisection: Output
# %end

# %option
# % key: output_prefix
# % type: string
# % required: no
# % description: Prefix for individual mineral indicator output maps (requires -m flag)
# % guisection: Output
# %end

# %option
# % key: min_wavelength
# % type: double
# % required: no
# % description: Minimum wavelength to consider (nm); overrides sensor range
# % guisection: Processing
# %end

# %option
# % key: max_wavelength
# % type: double
# % required: no
# % description: Maximum wavelength to consider (nm); overrides sensor range
# % guisection: Processing
# %end

# %flag
# % key: n
# % description: Only include bands marked as valid (valid=1)
# % guisection: Processing
# %end

# %flag
# % key: m
# % description: Output individual mineral indicator maps (output_prefix required)
# % guisection: Output
# %end

# %flag
# % key: i
# % description: Info mode - print spectral coverage and diagnostic capabilities without processing
# % guisection: Processing
# %end

# %flag
# % key: v
# % description: Verbose reporting of mineral indicator scores per class
# % guisection: Processing
# %end

import sys
import os
import re
import grass.script as gs

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROCK_FAMILY_CLASSES = {
    0: "Masked (vegetation/water)",
    1: "Mafic",
    2: "Ultramafic",
    3: "Felsic",
    4: "Intermediate",
    5: "Carbonate sedimentary",
    6: "Siliciclastic sedimentary",
    7: "Metamorphic",
    8: "Evaporite/Sulphate",
    9: "Uncertain/Mixed",
}

WEATHERING_CLASSES = {
    0: "W0 Fresh",
    1: "W1 Slightly weathered",
    2: "W2 Moderately weathered",
    3: "W3 Highly weathered",
    4: "W4 Completely weathered (saprolite)",
    5: "W5 Residual soil / laterite",
}

ALTERATION_CLASSES = {
    1: "Unaltered",
    2: "Propylitic",
    3: "Phyllic",
    4: "Argillic",
    5: "Advanced argillic",
    6: "Supergene",
    7: "AMD active",
    8: "AMD mature",
    9: "Carbonate alteration",
    10: "Serpentinization",
}

# ---------------------------------------------------------------------------
# Band metadata helpers (shared pattern with i.hyper.albedo)
# ---------------------------------------------------------------------------

def get_raster3d_info(raster3d):
    """Get information about 3D raster."""
    try:
        info = gs.raster3d_info(raster3d)
        return info
    except Exception as e:
        gs.fatal(f"Cannot get info for 3D raster {raster3d}: {e}")


def parse_wavelength_from_metadata(raster3d, band_num):
    """Parse wavelength and validity from band metadata."""
    band_name = f"{raster3d}#{band_num}"
    wavelength = None
    fwhm = None
    valid = True
    unit = "nm"
    try:
        result = gs.read_command('r.info', map=band_name, flags='h')
        for line in result.split('\n'):
            line = line.strip()
            if line.startswith('wavelength='):
                wavelength = float(line.split('=')[1])
            elif line.startswith('FWHM='):
                fwhm = float(line.split('=')[1])
            elif line.startswith('valid='):
                valid = int(line.split('=')[1]) == 1
            elif line.startswith('unit='):
                unit = line.split('=')[1].strip()
    except Exception:
        pass
    return wavelength, fwhm, valid, unit


def parse_wavelengths_from_3d_comments(raster3d):
    """Parse band wavelengths from the 3D raster's own r3.info comments.

    Supports the format written by r3.in.bin-based workflows:
        Band N: WAVELENGTH nm, FWHM: FWHM_VAL nm

    Returns a dict mapping band_num (int) -> (wavelength, fwhm, valid, unit).
    Returns an empty dict if the format is not recognised.
    """
    try:
        info_text = gs.read_command('r3.info', map=raster3d)
    except Exception:
        return {}
    pattern = re.compile(
        r'Band\s+(\d+):\s+([\d.]+)\s+nm[,\s]+FWHM:\s+([\d.]+)\s+nm'
    )
    bands = {}
    for line in info_text.split('\n'):
        m = pattern.search(line)
        if m:
            band_num = int(m.group(1))
            bands[band_num] = (float(m.group(2)), float(m.group(3)), True, 'nm')
    return bands


def convert_wavelength_to_nm(wavelength, unit):
    """Convert wavelength to nanometers."""
    unit = unit.lower().strip()
    if unit in ['nm', 'nanometer', 'nanometers']:
        return wavelength
    elif unit in ['um', 'µm', 'micrometer', 'micrometers', 'micron', 'microns']:
        return wavelength * 1000.0
    elif unit in ['m', 'meter', 'meters']:
        return wavelength * 1e9
    else:
        gs.warning(f"Unknown wavelength unit '{unit}', assuming nanometers")
        return wavelength


def get_all_band_wavelengths(raster3d, only_valid=False, min_wl=None, max_wl=None):
    """Extract all band wavelengths and metadata from 3D raster.

    Each returned band dict contains a 'map_name' key:
    - When 2D band-slice rasters exist (i.hyper.import workflow), map_name is set
      to the slice raster name ({raster3d}#{band_num}).
    - When they do not exist (r3.in.bin / direct import workflow), map_name is
      None; call extract_band_slices() before computing indicators.
    """
    info = get_raster3d_info(raster3d)
    depths = int(info['depths'])
    bands = []
    gs.verbose(f"Scanning {depths} bands for wavelength metadata...")

    # Check upfront whether 2D band-slice rasters exist (silent, no ERRORs).
    base_name = raster3d.split('@')[0]
    mapset = raster3d.split('@')[1] if '@' in raster3d else None
    slice_check = gs.find_file(f"{base_name}#1", element='cell', mapset=mapset)
    slices_exist = bool(slice_check.get('name'))

    if slices_exist:
        # Standard i.hyper.import path: metadata from 2D slice rasters.
        for i in range(1, depths + 1):
            wavelength, fwhm, valid, unit = parse_wavelength_from_metadata(raster3d, i)
            if wavelength is None:
                continue
            wavelength_nm = convert_wavelength_to_nm(wavelength, unit)
            if min_wl is not None and wavelength_nm < min_wl:
                continue
            if max_wl is not None and wavelength_nm > max_wl:
                continue
            if only_valid and not valid:
                continue
            bands.append({
                'band_num': i,
                'wavelength': wavelength_nm,
                'fwhm': fwhm if fwhm else 0,
                'valid': valid,
                'unit': unit,
                'map_name': f"{raster3d}#{i}",
            })
    else:
        # Fallback: wavelengths from the 3D raster's own comment block.
        gs.verbose("Band slice rasters not found; reading metadata from 3D raster comments.")
        wl_dict = parse_wavelengths_from_3d_comments(raster3d)
        for i in range(1, depths + 1):
            if i not in wl_dict:
                continue
            wavelength, fwhm, valid, unit = wl_dict[i]
            wavelength_nm = convert_wavelength_to_nm(wavelength, unit)
            if min_wl is not None and wavelength_nm < min_wl:
                continue
            if max_wl is not None and wavelength_nm > max_wl:
                continue
            if only_valid and not valid:
                continue
            bands.append({
                'band_num': i,
                'wavelength': wavelength_nm,
                'fwhm': fwhm if fwhm else 0,
                'valid': valid,
                'unit': unit,
                'map_name': None,  # filled by extract_band_slices()
            })

    if not bands:
        gs.fatal("No wavelength metadata found in 3D raster bands. "
                 "Ensure input was created by i.hyper.import or contains "
                 "'Band N: WL nm, FWHM: F nm' lines in its r3.info comments.")
    bands.sort(key=lambda x: x['wavelength'])
    return bands


def extract_band_slices(raster3d, bands, pid, tmp_maps):
    """Extract 2D band slices from a 3D raster using r3.to.rast.

    Updates each band dict's 'map_name' in-place.
    Called only when band slice rasters were not created by i.hyper.import.

    r3.to.rast requires the 3D computational region to match the 3D raster.
    The current region is saved before modification and restored afterwards.
    Map names produced by r3.to.rast are discovered via g.list so the code
    is robust to GRASS version differences in naming convention.
    """
    prefix = make_tmp_name(pid, 'bslice')
    saved_region = make_tmp_name(pid, 'saved_region')

    # Save current region, align to 3D raster, extract, then restore.
    gs.run_command('g.region', save=saved_region, overwrite=True, quiet=True)
    try:
        gs.run_command('g.region', raster3d=raster3d, quiet=True)
        gs.message("Extracting 2D band slices from 3D raster (one-time operation)...")
        gs.run_command('r3.to.rast', input=raster3d, output=prefix,
                       overwrite=True, quiet=True)
    finally:
        gs.run_command('g.region', region=saved_region, quiet=True)
        gs.run_command('g.remove', type='region', name=saved_region,
                       flags='f', quiet=True)

    # Discover what r3.to.rast actually named the output maps (naming varies
    # across GRASS versions; g.list returns them in alphabetical = depth order).
    created = sorted(gs.read_command(
        'g.list', type='raster', pattern=f"{prefix}_*", quiet=True,
    ).split())

    if not created:
        gs.fatal(
            f"r3.to.rast created no output maps matching '{prefix}_*'. "
            "Ensure the mapset is writable and the 3D raster is valid."
        )

    # Register all created maps for cleanup.
    tmp_maps.extend(created)

    # Map band_num -> created map name. r3.to.rast outputs bottom-to-top
    # (depth 1 = first band = created[0], depth N = last band = created[-1]).
    band_num_to_map = {i + 1: name for i, name in enumerate(created)}
    for b in bands:
        b['map_name'] = band_num_to_map.get(b['band_num'])


def find_band(bands, target_wl, tolerance_nm=25):
    """Return closest band dict within tolerance_nm of target_wl, or None."""
    best = None
    best_dist = tolerance_nm + 1
    for b in bands:
        dist = abs(b['wavelength'] - target_wl)
        if dist <= tolerance_nm and dist < best_dist:
            best_dist = dist
            best = b
    return best


def band_map_name(raster3d, band_num):
    """Return the 2D raster slice name for a given band number."""
    return f"{raster3d}#{band_num}"


# ---------------------------------------------------------------------------
# Coverage assessment
# ---------------------------------------------------------------------------

def assess_coverage(bands):
    """Return dict with coverage flags and band counts per spectral region."""
    wls = [b['wavelength'] for b in bands]
    wl_min = min(wls)
    wl_max = max(wls)

    def count_in(lo, hi):
        return sum(1 for w in wls if lo <= w <= hi)

    cov = {
        'wl_min': wl_min,
        'wl_max': wl_max,
        'n_total': len(bands),
        'vnir': count_in(400, 1000),
        'nir_fe2': count_in(900, 1100),
        'swir_oh1400': count_in(1350, 1450),
        'swir_h2o1900': count_in(1800, 2000),
        'swir_aloh': count_in(2100, 2300),
        'swir_mgoh': count_in(2250, 2400),
        'swir_co3': count_in(2290, 2400),
    }
    cov['has_vnir'] = cov['vnir'] > 0
    cov['has_nir'] = cov['nir_fe2'] > 0
    cov['has_swir_oh1400'] = cov['swir_oh1400'] > 0
    cov['has_swir_h2o1900'] = cov['swir_h2o1900'] > 0
    cov['has_swir_aloh'] = cov['swir_aloh'] > 0
    cov['has_swir_mgoh'] = cov['swir_mgoh'] > 0
    cov['has_swir_co3'] = cov['swir_co3'] > 0
    cov['full_swir'] = (cov['has_swir_aloh'] and cov['has_swir_mgoh']
                        and cov['has_swir_co3'])
    return cov


def print_info(bands, cov):
    """Print spectral coverage and capability table (-i flag)."""
    sep = "=" * 62

    def avail(flag, n=None):
        if flag:
            return f"AVAILABLE{(' - ' + str(n) + ' bands') if n is not None else ''}"
        return "NOT AVAILABLE"

    gs.message(sep)
    gs.message("i.hyper.geology - Geological Assessment Capabilities")
    gs.message(sep)
    gs.message(f"Sensor spectral coverage: {cov['wl_min']:.1f} - {cov['wl_max']:.1f} nm "
               f"({cov['n_total']} bands)")
    gs.message(" ")
    gs.message("Spectral Region Coverage:")
    gs.message(f"  VNIR Fe-oxide (400-1000 nm):   {avail(cov['has_vnir'], cov['vnir'])}")
    gs.message(f"  NIR Fe2+ (900-1100 nm):         {avail(cov['has_nir'], cov['nir_fe2'])}")
    gs.message(f"  SWIR OH/H2O (1350-1450 nm):     {avail(cov['has_swir_oh1400'], cov['swir_oh1400'])}")
    gs.message(f"  SWIR H2O (1800-2000 nm):        {avail(cov['has_swir_h2o1900'], cov['swir_h2o1900'])}")
    gs.message(f"  SWIR Al-OH (2100-2300 nm):      {avail(cov['has_swir_aloh'], cov['swir_aloh'])}")
    gs.message(f"  SWIR Mg-OH (2250-2400 nm):      {avail(cov['has_swir_mgoh'], cov['swir_mgoh'])}")
    gs.message(f"  SWIR CO3 (2290-2400 nm):        {avail(cov['has_swir_co3'], cov['swir_co3'])}")
    gs.message(" ")

    full_label = "FULL (all regions available)" if (cov['has_vnir'] and cov['full_swir']) else "PARTIAL"
    gs.message("Geological Assessment Capabilities:")
    gs.message(f"  Rock family classification:    {full_label if cov['has_vnir'] and cov['full_swir'] else 'PARTIAL - missing regions reduce accuracy'}")
    gs.message(f"  Weathering grade (W0-W5):      {'FULL' if cov['has_vnir'] and cov['has_swir_aloh'] else 'PARTIAL'}")
    gs.message(f"  AMD detection:                 {'FULL (VNIR available)' if cov['has_vnir'] else 'NOT AVAILABLE (no VNIR)'}")
    gs.message(f"  Hydrothermal alteration:       {'FULL (SWIR available)' if cov['full_swir'] else 'PARTIAL'}")
    gs.message(f"  Al-OH position mapping:        {'FULL' if cov['has_swir_aloh'] else 'NOT AVAILABLE'}")
    gs.message(f"  Mg-OH mapping:                 {'FULL' if cov['has_swir_mgoh'] else 'NOT AVAILABLE'}")
    gs.message(f"  Carbonate mapping:             {'FULL' if cov['has_swir_co3'] else 'NOT AVAILABLE'}")
    gs.message(" ")

    def yes_no(b):
        return "YES" if b else "NO"

    has_jarosite = find_band(bands, 430) is not None and find_band(bands, 530) is not None
    has_hematite = find_band(bands, 630) is not None and find_band(bands, 490) is not None
    has_goethite = find_band(bands, 900, 50) is not None
    has_pyroxene = find_band(bands, 1000, 50) is not None
    has_kaolinite = find_band(bands, 2165, 30) is not None and find_band(bands, 2205, 30) is not None
    has_mica = find_band(bands, 2200, 30) is not None
    has_chlorite = find_band(bands, 2320, 30) is not None
    has_calcite = find_band(bands, 2340, 30) is not None
    has_gypsum = find_band(bands, 1750, 30) is not None
    has_alunite = find_band(bands, 2270, 30) is not None

    gs.message("Mineral Indicators Available:")
    gs.message(f"  Jarosite (430/900 nm):          {yes_no(has_jarosite)}")
    gs.message(f"  Hematite (530/630 nm):          {yes_no(has_hematite)}")
    gs.message(f"  Goethite (900 nm):              {yes_no(has_goethite)}")
    gs.message(f"  Pyroxene/Olivine (1000 nm):     {yes_no(has_pyroxene)}")
    gs.message(f"  Kaolinite (2165/2205 nm):       {yes_no(has_kaolinite)}")
    gs.message(f"  White Mica (2195-2220 nm):      {yes_no(has_mica)}")
    gs.message(f"  Chlorite/Serpentine (2320 nm):  {yes_no(has_chlorite)}")
    gs.message(f"  Calcite (2340 nm):              {yes_no(has_calcite)}")
    gs.message(f"  Gypsum (1750 nm):               {yes_no(has_gypsum)}")
    gs.message(f"  Alunite (2270 nm):              {yes_no(has_alunite)}")
    gs.message(sep)


# ---------------------------------------------------------------------------
# Temp map management
# ---------------------------------------------------------------------------

def make_tmp_name(pid, label):
    return f"tmp_ihgeology_{pid}_{label}"


def remove_tmp_maps(tmp_maps):
    """Remove all temporary raster maps silently."""
    if not tmp_maps:
        return
    existing = []
    for m in tmp_maps:
        try:
            gs.run_command('g.remove', type='raster', name=m, flags='f',
                           quiet=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Spectral indicator computation
# ---------------------------------------------------------------------------

def compute_band_depth(pid, label, band_l, band_c, band_r, tmp_maps,
                       clamp_zero=True):
    """Compute normalized band depth: 1 - rho_c / mean(rho_l, rho_r).

    Returns the name of the temp raster created, or None on failure.
    Clamps negative values to 0 when clamp_zero=True.
    """
    out = make_tmp_name(pid, label)
    bl, bc, br = f'"{band_l}"', f'"{band_c}"', f'"{band_r}"'
    if clamp_zero:
        expr = (f"{out} = max(0.0, 1.0 - {bc} / "
                f"(({bl} + {br}) / 2.0))")
    else:
        expr = (f"{out} = 1.0 - {bc} / "
                f"(({bl} + {br}) / 2.0)")
    try:
        gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
        tmp_maps.append(out)
        return out
    except Exception as e:
        gs.warning(f"Failed to compute band depth '{label}': {e}")
        return None


def compute_ratio(pid, label, band_a, band_b, tmp_maps):
    """Compute simple ratio band_a / band_b."""
    out = make_tmp_name(pid, label)
    ba, bb = f'"{band_a}"', f'"{band_b}"'
    expr = f"{out} = if({bb} != 0, {ba} / {bb}, 1.0)"
    try:
        gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
        tmp_maps.append(out)
        return out
    except Exception as e:
        gs.warning(f"Failed to compute ratio '{label}': {e}")
        return None


def compute_constant(pid, label, value, tmp_maps):
    """Create a constant raster (used when bands are missing)."""
    out = make_tmp_name(pid, label)
    expr = f"{out} = float({value})"
    try:
        gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
        tmp_maps.append(out)
        return out
    except Exception as e:
        gs.warning(f"Failed to create constant map '{label}': {e}")
        return None


def compute_all_indicators(raster3d, bands, pid, tmp_maps, verbose=False):
    """Compute all spectral indicator maps. Returns dict of indicator_name -> map_name."""

    def bm(b):
        """Band map name for a band dict."""
        return b['map_name'] or band_map_name(raster3d, b['band_num'])

    def fb(wl, tol=25):
        return find_band(bands, wl, tol)

    indicators = {}

    gs.message("  Computing VNIR indicators...")
    gs.percent(0, 15, 1)

    # 1. jarosite_vnir: band depth at 430 nm using 400, 430, 470 nm
    b400 = fb(400); b430 = fb(430); b470 = fb(470)
    if b400 and b430 and b470:
        m = compute_band_depth(pid, 'jarosite_vnir', bm(b400), bm(b430), bm(b470), tmp_maps)
        if verbose:
            gs.verbose(f"    jarosite_vnir: bands {b400['wavelength']:.1f}/{b430['wavelength']:.1f}/{b470['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'jarosite_vnir', 0.0, tmp_maps)
        if not (b400 and b430 and b470):
            gs.warning("VNIR jarosite indicator skipped: insufficient bands near 400/430/470 nm")
    indicators['jarosite_vnir'] = m

    # 2. hematite_vnir: ratio rho630/rho490
    b490 = fb(490); b630 = fb(630)
    if b490 and b630:
        m = compute_ratio(pid, 'hematite_vnir', bm(b630), bm(b490), tmp_maps)
        if verbose:
            gs.verbose(f"    hematite_vnir: ratio {b630['wavelength']:.1f}/{b490['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'hematite_vnir', 1.0, tmp_maps)
        gs.warning("Hematite ratio skipped: bands near 490/630 nm not found")
    indicators['hematite_vnir'] = m

    # 3. goethite_900: band depth at 900 nm (750, 900, 1050)
    b750 = fb(750); b900 = fb(900, 50); b1050 = fb(1050, 50)
    if b750 and b900 and b1050:
        m = compute_band_depth(pid, 'goethite_900', bm(b750), bm(b900), bm(b1050), tmp_maps)
        if verbose:
            gs.verbose(f"    goethite_900: bands {b750['wavelength']:.1f}/{b900['wavelength']:.1f}/{b1050['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'goethite_900', 0.0, tmp_maps)
        gs.warning("Goethite 900 nm indicator skipped: insufficient bands near 750/900/1050 nm")
    indicators['goethite_900'] = m

    # 4. fe_oxide_broad: ratio rho750/rho550
    b550 = fb(550)
    if b750 and b550:
        m = compute_ratio(pid, 'fe_oxide_broad', bm(b750), bm(b550), tmp_maps)
        if verbose:
            gs.verbose(f"    fe_oxide_broad: ratio {b750['wavelength']:.1f}/{b550['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'fe_oxide_broad', 1.0, tmp_maps)
        gs.warning("Fe-oxide broad ratio skipped: bands near 550/750 nm not found")
    indicators['fe_oxide_broad'] = m

    # 5. ferrous_1000: band depth at 1000 nm (850, 1000, 1200) - pyroxene/olivine
    b850 = fb(850); b1000 = fb(1000, 50); b1200 = fb(1200, 50)
    if b850 and b1000 and b1200:
        m = compute_band_depth(pid, 'ferrous_1000', bm(b850), bm(b1000), bm(b1200), tmp_maps)
        if verbose:
            gs.verbose(f"    ferrous_1000: bands {b850['wavelength']:.1f}/{b1000['wavelength']:.1f}/{b1200['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'ferrous_1000', 0.0, tmp_maps)
        gs.warning("Ferrous iron 1000 nm indicator skipped: insufficient bands near 850/1000/1200 nm")
    indicators['ferrous_1000'] = m

    # NDVI mask: (rho800 - rho678) / (rho800 + rho678)
    b678 = fb(678); b800 = fb(800)
    if b678 and b800:
        out_ndvi = make_tmp_name(pid, 'ndvi')
        q800, q678 = f'"{bm(b800)}"', f'"{bm(b678)}"'
        expr = (f"{out_ndvi} = if(({q800} + {q678}) != 0, "
                f"({q800} - {q678}) / ({q800} + {q678}), 0.0)")
        try:
            gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
            tmp_maps.append(out_ndvi)
            if verbose:
                gs.verbose(f"    ndvi: bands {b678['wavelength']:.1f}/{b800['wavelength']:.1f} nm")
        except Exception as e:
            gs.warning(f"NDVI computation failed: {e}")
            out_ndvi = compute_constant(pid, 'ndvi', 0.0, tmp_maps)
    else:
        out_ndvi = compute_constant(pid, 'ndvi', 0.0, tmp_maps)
        gs.warning("NDVI vegetation mask skipped: bands near 678/800 nm not found")
    indicators['ndvi'] = out_ndvi

    gs.message("  Computing SWIR indicators...")
    gs.percent(3, 15, 1)

    # 6. hydroxyl_1400: depth at 1400 nm (1350, 1400, 1500)
    b1350 = fb(1350); b1400 = fb(1400); b1500 = fb(1500)
    if b1350 and b1400 and b1500:
        m = compute_band_depth(pid, 'hydroxyl_1400', bm(b1350), bm(b1400), bm(b1500), tmp_maps)
        if verbose:
            gs.verbose(f"    hydroxyl_1400: bands {b1350['wavelength']:.1f}/{b1400['wavelength']:.1f}/{b1500['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'hydroxyl_1400', 0.0, tmp_maps)
        gs.warning("OH 1400 nm indicator skipped: insufficient bands near 1350/1400/1500 nm")
    indicators['hydroxyl_1400'] = m

    # 7. water_1900: depth at 1900 nm (1800, 1900, 2000)
    b1800 = fb(1800); b1900 = fb(1900); b2000 = fb(2000)
    if b1800 and b1900 and b2000:
        m = compute_band_depth(pid, 'water_1900', bm(b1800), bm(b1900), bm(b2000), tmp_maps)
        if verbose:
            gs.verbose(f"    water_1900: bands {b1800['wavelength']:.1f}/{b1900['wavelength']:.1f}/{b2000['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'water_1900', 0.0, tmp_maps)
        gs.warning("H2O 1900 nm indicator skipped: insufficient bands near 1800/1900/2000 nm")
    indicators['water_1900'] = m

    # 8. gypsum_1750: depth at 1750 nm (1700, 1750, 1800)
    b1700 = fb(1700); b1750 = fb(1750); b1800b = fb(1800)
    if b1700 and b1750 and b1800b:
        m = compute_band_depth(pid, 'gypsum_1750', bm(b1700), bm(b1750), bm(b1800b), tmp_maps)
        if verbose:
            gs.verbose(f"    gypsum_1750: bands {b1700['wavelength']:.1f}/{b1750['wavelength']:.1f}/{b1800b['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'gypsum_1750', 0.0, tmp_maps)
        gs.warning("Gypsum 1750 nm indicator skipped: insufficient bands near 1700/1750/1800 nm")
    indicators['gypsum_1750'] = m

    gs.percent(6, 15, 1)

    # 9. aloh_2200: depth at 2200 nm (2100, 2200, 2280)
    b2100 = fb(2100); b2200 = fb(2200); b2280 = fb(2280)
    if b2100 and b2200 and b2280:
        m = compute_band_depth(pid, 'aloh_2200', bm(b2100), bm(b2200), bm(b2280), tmp_maps)
        if verbose:
            gs.verbose(f"    aloh_2200: bands {b2100['wavelength']:.1f}/{b2200['wavelength']:.1f}/{b2280['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'aloh_2200', 0.0, tmp_maps)
        gs.warning("Al-OH 2200 nm indicator skipped: insufficient bands near 2100/2200/2280 nm")
    indicators['aloh_2200'] = m

    # 10. aloh_position: ratio rho2165/rho2220 (>1 => kaolinite; <1 => muscovite)
    b2165 = fb(2165); b2220 = fb(2220)
    if b2165 and b2220:
        m = compute_ratio(pid, 'aloh_position', bm(b2165), bm(b2220), tmp_maps)
        if verbose:
            gs.verbose(f"    aloh_position: ratio {b2165['wavelength']:.1f}/{b2220['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'aloh_position', 1.0, tmp_maps)
        gs.warning("Al-OH position ratio skipped: bands near 2165/2220 nm not found")
    indicators['aloh_position'] = m

    # 11. alunite_2270: depth at 2270 nm (2220, 2270, 2310)
    b2270 = fb(2270); b2310 = fb(2310)
    if b2220 and b2270 and b2310:
        m = compute_band_depth(pid, 'alunite_2270', bm(b2220), bm(b2270), bm(b2310), tmp_maps)
        if verbose:
            gs.verbose(f"    alunite_2270: bands {b2220['wavelength']:.1f}/{b2270['wavelength']:.1f}/{b2310['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'alunite_2270', 0.0, tmp_maps)
        gs.warning("Alunite 2270 nm indicator skipped: insufficient bands near 2220/2270/2310 nm")
    indicators['alunite_2270'] = m

    gs.percent(9, 15, 1)

    # 12. mgoh_2300: depth at 2320 nm (2250, 2320, 2400)
    b2250 = fb(2250); b2320 = fb(2320); b2400 = fb(2400, 30)
    if b2250 and b2320 and b2400:
        m = compute_band_depth(pid, 'mgoh_2300', bm(b2250), bm(b2320), bm(b2400), tmp_maps)
        if verbose:
            gs.verbose(f"    mgoh_2300: bands {b2250['wavelength']:.1f}/{b2320['wavelength']:.1f}/{b2400['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'mgoh_2300', 0.0, tmp_maps)
        gs.warning("Mg-OH 2300 nm indicator skipped: insufficient bands near 2250/2320/2400 nm")
    indicators['mgoh_2300'] = m

    # 13. carbonate_2340: depth at 2340 nm (2290, 2340, 2400)
    b2290 = fb(2290); b2340 = fb(2340)
    if b2290 and b2340 and b2400:
        m = compute_band_depth(pid, 'carbonate_2340', bm(b2290), bm(b2340), bm(b2400), tmp_maps)
        if verbose:
            gs.verbose(f"    carbonate_2340: bands {b2290['wavelength']:.1f}/{b2340['wavelength']:.1f}/{b2400['wavelength']:.1f} nm")
    else:
        m = compute_constant(pid, 'carbonate_2340', 0.0, tmp_maps)
        gs.warning("Carbonate 2340 nm indicator skipped: insufficient bands near 2290/2340/2400 nm")
    indicators['carbonate_2340'] = m

    gs.percent(12, 15, 1)

    # 14. reactivity_index: (rho2210 + rho2395) / (rho2285 + rho2330) - Tolentino et al. 2025
    b2210 = fb(2210); b2395 = fb(2395); b2285 = fb(2285); b2330 = fb(2330)
    if b2210 and b2395 and b2285 and b2330:
        out_ri = make_tmp_name(pid, 'reactivity_index')
        q2210, q2395 = f'"{bm(b2210)}"', f'"{bm(b2395)}"'
        q2285, q2330 = f'"{bm(b2285)}"', f'"{bm(b2330)}"'
        expr = (f"{out_ri} = if(({q2285} + {q2330}) != 0, "
                f"({q2210} + {q2395}) / ({q2285} + {q2330}), 1.0)")
        try:
            gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
            tmp_maps.append(out_ri)
            if verbose:
                gs.verbose(f"    reactivity_index: (b{b2210['wavelength']:.0f}+b{b2395['wavelength']:.0f})/(b{b2285['wavelength']:.0f}+b{b2330['wavelength']:.0f})")
        except Exception as e:
            gs.warning(f"Reactivity index failed: {e}")
            out_ri = compute_constant(pid, 'reactivity_index', 1.0, tmp_maps)
    else:
        out_ri = compute_constant(pid, 'reactivity_index', 1.0, tmp_maps)
        gs.warning("Reactivity index skipped: insufficient bands near 2210/2285/2330/2395 nm")
    indicators['reactivity_index'] = out_ri

    # 15. clay_mixture_index: (rho2168 * rho2224) / rho2198 - Tolentino et al. 2025
    b2168 = fb(2168); b2224 = fb(2224); b2198 = fb(2198)
    if b2168 and b2224 and b2198:
        out_cmi = make_tmp_name(pid, 'clay_mixture_index')
        q2168, q2224, q2198 = f'"{bm(b2168)}"', f'"{bm(b2224)}"', f'"{bm(b2198)}"'
        expr = (f"{out_cmi} = if({q2198} != 0, "
                f"({q2168} * {q2224}) / {q2198}, 1.0)")
        try:
            gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
            tmp_maps.append(out_cmi)
            if verbose:
                gs.verbose(f"    clay_mixture_index: (b{b2168['wavelength']:.0f}*b{b2224['wavelength']:.0f})/b{b2198['wavelength']:.0f}")
        except Exception as e:
            gs.warning(f"Clay mixture index failed: {e}")
            out_cmi = compute_constant(pid, 'clay_mixture_index', 1.0, tmp_maps)
    else:
        out_cmi = compute_constant(pid, 'clay_mixture_index', 1.0, tmp_maps)
        gs.warning("Clay mixture index skipped: insufficient bands near 2168/2198/2224 nm")
    indicators['clay_mixture_index'] = out_cmi

    gs.percent(15, 15, 1)
    return indicators


# ---------------------------------------------------------------------------
# Rock family classification scoring
# ---------------------------------------------------------------------------

def build_class_scores(pid, indicators, tmp_maps, verbose=False):
    """Build per-class score maps using weighted indicator sums.

    Returns dict of class_id -> score_map_name.
    """
    ind = indicators

    # Helpers for concise r.mapcalc expressions
    def I(key):
        return ind[key]

    scores = {}

    # Class 1: Mafic
    # Fe2+ at 1000 nm + Mg-OH at 2320 nm (chlorite alteration)
    # Fe-oxide coatings (goethite/hematite)
    out = make_tmp_name(pid, 'score_mafic')
    expr = (f"{out} = "
            f"0.40 * {I('ferrous_1000')} + "
            f"0.25 * {I('goethite_900')} + "
            f"0.20 * {I('mgoh_2300')} + "
            f"0.15 * (if({I('hematite_vnir')} > 1.1, {I('hematite_vnir')} - 1.1, 0.0))")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
    tmp_maps.append(out)
    scores[1] = out

    # Class 2: Ultramafic
    # Strong Mg-OH (serpentine/talc), no significant Al-OH, Fe2+ at 900/1050
    out = make_tmp_name(pid, 'score_ultramafic')
    expr = (f"{out} = "
            f"0.45 * {I('mgoh_2300')} + "
            f"0.30 * {I('ferrous_1000')} + "
            f"0.25 * (if({I('aloh_2200')} < 0.03, 0.1, 0.0))")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
    tmp_maps.append(out)
    scores[2] = out

    # Class 3: Felsic
    # Al-OH dominant (muscovite 2195-2220 nm position), alunite/kaolinite possible
    out = make_tmp_name(pid, 'score_felsic')
    expr = (f"{out} = "
            f"0.45 * {I('aloh_2200')} + "
            f"0.20 * (if({I('aloh_position')} <= 1.0, 0.05, {I('aloh_position')} - 1.0)) + "
            f"0.20 * {I('alunite_2270')} + "
            f"0.15 * (if({I('ferrous_1000')} < 0.05, 0.1, 0.0))")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
    tmp_maps.append(out)
    scores[3] = out

    # Class 4: Intermediate
    # Mixed mafic/felsic: moderate Fe2+ + moderate Al-OH + hornblende (Mg-OH + Al-OH)
    out = make_tmp_name(pid, 'score_intermediate')
    expr = (f"{out} = "
            f"0.30 * {I('aloh_2200')} + "
            f"0.30 * {I('ferrous_1000')} + "
            f"0.25 * {I('mgoh_2300')} + "
            f"0.15 * {I('goethite_900')}")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
    tmp_maps.append(out)
    scores[4] = out

    # Class 5: Carbonate sedimentary
    # Strong CO3 2340 nm, minimal Al-OH, possible H2O
    out = make_tmp_name(pid, 'score_carbonate')
    expr = (f"{out} = "
            f"0.55 * {I('carbonate_2340')} + "
            f"0.25 * {I('water_1900')} + "
            f"0.20 * (if({I('aloh_2200')} < 0.04, 0.1, 0.0))")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
    tmp_maps.append(out)
    scores[5] = out

    # Class 6: Siliciclastic sedimentary
    # Clay minerals (kaolinite/illite), possible Fe-staining, shale
    out = make_tmp_name(pid, 'score_siliciclastic')
    expr = (f"{out} = "
            f"0.40 * {I('aloh_2200')} + "
            f"0.25 * {I('clay_mixture_index')} * 0.1 + "
            f"0.20 * {I('goethite_900')} + "
            f"0.15 * (if({I('carbonate_2340')} < 0.06, 0.05, 0.0))")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
    tmp_maps.append(out)
    scores[6] = out

    # Class 7: Metamorphic
    # Mica + chlorite + amphibole (Mg-OH), no dominant Fe-oxide, no strong carbonate
    out = make_tmp_name(pid, 'score_metamorphic')
    expr = (f"{out} = "
            f"0.35 * {I('aloh_2200')} + "
            f"0.35 * {I('mgoh_2300')} + "
            f"0.20 * (if({I('goethite_900')} < 0.05, 0.1, 0.0)) + "
            f"0.10 * (if({I('carbonate_2340')} < 0.04, 0.05, 0.0))")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
    tmp_maps.append(out)
    scores[7] = out

    # Class 8: Evaporite/Sulphate
    # Gypsum 1750 nm + alunite 2270 nm + jarosite VNIR
    out = make_tmp_name(pid, 'score_evaporite')
    expr = (f"{out} = "
            f"0.40 * {I('gypsum_1750')} + "
            f"0.30 * {I('alunite_2270')} + "
            f"0.30 * {I('jarosite_vnir')}")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)
    tmp_maps.append(out)
    scores[8] = out

    return scores


def build_family_classification(pid, indicators, scores, tmp_maps, output_name):
    """Build the final rock family classification using priority-ordered rules.

    Priority: Evaporite(8) > Carbonate(5) > Ultramafic(2) > Mafic(1) >
              Metamorphic(7) > Felsic(3) > Intermediate(4) > Siliciclastic(6) > Uncertain(9)
    Class 0 = masked (NDVI > 0.3)
    """
    ind = indicators
    MIN_SCORE = 0.15

    # Build nested if expression: priority order
    # Winner = highest score among classes above MIN_SCORE threshold, with priority tie-breaking
    # We implement this as: mask first, then check scores in priority order
    # For each class: if score > MIN_SCORE AND score >= all higher-priority class scores -> assign

    def S(cid):
        return scores[cid]

    # The expression selects the class with the highest score among those >= MIN_SCORE.
    # Priority order is applied as tie-breaker via >= vs > comparisons.
    # Priority: 8 > 5 > 2 > 1 > 7 > 3 > 4 > 6 > 9(uncertain)
    # We build from lowest priority upward (innermost if = lowest priority).
    priority_order = [6, 4, 3, 7, 1, 2, 5, 8]  # lowest to highest priority

    # Start with uncertain = 9
    inner = "9"
    for cid in priority_order:
        inner = (f"if({S(cid)} >= {MIN_SCORE} && {S(cid)} >= {inner.split('if')[0].strip() if inner != '9' else '0'}, "
                 f"{cid}, {inner})")

    # Simpler, cleaner approach: use explicit max scoring
    # Build max-score comparison for each class
    # For each class c, assign c if: score[c] = max(all scores) AND score[c] >= MIN_SCORE
    # Priority breaks ties by checking score >= (with strict > for lower priority)

    # Build the winner expression step by step
    # winner_expr resolves to the integer class
    all_score_maps = [S(c) for c in [1, 2, 3, 4, 5, 6, 7, 8]]

    # max score temp map
    max_score_map = make_tmp_name(pid, 'max_score')
    max_expr = (f"{max_score_map} = max({S(1)}, {S(2)}, {S(3)}, {S(4)}, "
                f"{S(5)}, {S(6)}, {S(7)}, {S(8)})")
    gs.run_command('r.mapcalc', expression=max_expr, overwrite=True, quiet=True)
    tmp_maps.append(max_score_map)

    # Build classification using priority order (higher priority classes checked first)
    # Priority (high to low): 8, 5, 2, 1, 7, 3, 4, 6
    pri_order = [8, 5, 2, 1, 7, 3, 4, 6]

    # innermost: siliciclastic (lowest priority, class 6)
    # Build from innermost (lowest priority) to outermost (highest priority)
    # For the lowest priority class, condition: score >= MIN_SCORE AND score == max_score
    # For higher priority: score >= MIN_SCORE AND score >= max_score (>= handles ties in their favor)

    def cond(cid, is_lowest):
        sc = S(cid)
        if is_lowest:
            return (f"if({sc} >= {MIN_SCORE} && {sc} >= {max_score_map}, "
                    f"{cid}, 9)")
        else:
            return None

    # Build nested if from lowest to highest priority
    expr_inner = f"if({S(6)} >= {MIN_SCORE} && {S(6)} >= {max_score_map}, 6, 9)"
    for cid in [4, 3, 7, 1, 2, 5, 8]:
        expr_inner = (f"if({S(cid)} >= {MIN_SCORE} && {S(cid)} >= {max_score_map}, "
                      f"{cid}, {expr_inner})")

    # Apply vegetation mask (NDVI > 0.3 -> class 0)
    ndvi_map = ind['ndvi']
    class_expr = f"if({ndvi_map} > 0.3, 0, {expr_inner})"

    final_expr = f"{output_name} = {class_expr}"
    gs.run_command('r.mapcalc', expression=final_expr, overwrite=True, quiet=True)


# ---------------------------------------------------------------------------
# Weathering grade mapping
# ---------------------------------------------------------------------------

def build_weathering_map(pid, indicators, output_name):
    """Build W0-W5 weathering grade map."""
    ind = indicators
    I = ind.__getitem__

    # Priority: W5 highest, W0 lowest. Build nested if from W0 outward.
    # W0: ferrous_1000 > 0.10 AND goethite_900 < 0.05 AND aloh_2200 < 0.05
    # W1: goethite_900 > 0.02 OR hematite_vnir > 1.2, ferrous_1000 > 0.05
    # W2: goethite_900 > 0.05 AND aloh_2200 > 0.03
    # W3: goethite_900 > 0.08 AND aloh_2200 > 0.06 AND ferrous_1000 < 0.05
    # W4: (goethite_900 > 0.10 OR fe_oxide_broad > 1.5) AND aloh_2200 > 0.08
    # W5: goethite_900 > 0.12 AND aloh_2200 > 0.10 AND ferrous_1000 < 0.02 AND fe_oxide_broad > 1.6

    w5_cond = (f"{I('goethite_900')} > 0.12 && "
               f"{I('aloh_2200')} > 0.10 && "
               f"{I('ferrous_1000')} < 0.02 && "
               f"{I('fe_oxide_broad')} > 1.6")
    w4_cond = (f"({I('goethite_900')} > 0.10 || {I('fe_oxide_broad')} > 1.5) && "
               f"{I('aloh_2200')} > 0.08")
    w3_cond = (f"{I('goethite_900')} > 0.08 && "
               f"{I('aloh_2200')} > 0.06 && "
               f"{I('ferrous_1000')} < 0.05")
    w2_cond = (f"{I('goethite_900')} > 0.05 && "
               f"{I('aloh_2200')} > 0.03")
    w1_cond = (f"({I('goethite_900')} > 0.02 || "
               f"{I('hematite_vnir')} > 1.2) && "
               f"{I('ferrous_1000')} > 0.05")
    w0_cond = (f"{I('ferrous_1000')} > 0.10 && "
               f"{I('goethite_900')} < 0.05 && "
               f"{I('aloh_2200')} < 0.05")

    expr = (f"{output_name} = "
            f"if({w5_cond}, 5, "
            f"if({w4_cond}, 4, "
            f"if({w3_cond}, 3, "
            f"if({w2_cond}, 2, "
            f"if({w1_cond}, 1, "
            f"if({w0_cond}, 0, 2))))))")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)


# ---------------------------------------------------------------------------
# Alteration type mapping
# ---------------------------------------------------------------------------

def build_alteration_map(pid, indicators, output_name):
    """Build alteration type map (1-10)."""
    ind = indicators
    I = ind.__getitem__

    # Priority order (high to low):
    # amd_active(7) > advanced_argillic(5) > serpentinization(10) > carbonate_alteration(9) >
    # amd_mature(8) > supergene(6) > propylitic(2) > phyllic(3) > argillic(4) > unaltered(1)

    # Conditions
    amd_active = (f"({I('jarosite_vnir')} > 0.05 || "
                  f"({I('gypsum_1750')} > 0.05 && {I('reactivity_index')} > 1.5))")
    adv_arg = (f"{I('alunite_2270')} > 0.04 && "
               f"{I('gypsum_1750')} > 0.03")
    serp = (f"{I('mgoh_2300')} > 0.08 && "
            f"{I('aloh_2200')} < 0.03")
    carb_alt = (f"{I('carbonate_2340')} > 0.06 && "
                f"{I('aloh_2200')} < 0.03 && "
                f"{I('mgoh_2300')} < 0.06")
    amd_mature = (f"{I('goethite_900')} > 0.08 && "
                  f"{I('water_1900')} > 0.10")
    supergene = (f"{I('goethite_900')} > 0.08 && "
                 f"{I('hematite_vnir')} > 1.3 && "
                 f"{I('jarosite_vnir')} < 0.04")
    propylitic = (f"{I('mgoh_2300')} > 0.06 && "
                  f"{I('carbonate_2340')} > 0.03")
    phyllic = (f"{I('aloh_2200')} > 0.06 && "
               f"{I('aloh_position')} >= 1.0")
    argillic = (f"{I('aloh_2200')} > 0.06 && "
                f"{I('aloh_position')} < 1.0")
    # unaltered = all indicators low
    unaltered = (f"{I('aloh_2200')} <= 0.04 && "
                 f"{I('mgoh_2300')} <= 0.04 && "
                 f"{I('goethite_900')} <= 0.04 && "
                 f"{I('gypsum_1750')} <= 0.02 && "
                 f"{I('jarosite_vnir')} <= 0.02")

    expr = (f"{output_name} = "
            f"if({amd_active}, 7, "
            f"if({adv_arg}, 5, "
            f"if({serp}, 10, "
            f"if({carb_alt}, 9, "
            f"if({amd_mature}, 8, "
            f"if({supergene}, 6, "
            f"if({propylitic}, 2, "
            f"if({phyllic}, 3, "
            f"if({argillic}, 4, "
            f"if({unaltered}, 1, 1))))))))))")
    gs.run_command('r.mapcalc', expression=expr, overwrite=True, quiet=True)


# ---------------------------------------------------------------------------
# Color tables and metadata
# ---------------------------------------------------------------------------

def set_family_colors(output_name):
    """Set color table for rock family classification."""
    color_rules = """\
0 200:200:200
1 255:140:0
2 180:0:0
3 255:182:193
4 255:160:122
5 135:206:235
6 210:180:140
7 128:0:128
8 255:215:0
9 255:255:255
"""
    gs.write_command('r.colors', map=output_name, rules='-',
                     stdin=color_rules, quiet=True)


def set_weathering_colors(output_name):
    """Set color table for weathering grade map."""
    color_rules = """\
0 cyan
1 green
2 yellow
3 orange
4 red
5 139:0:0
"""
    gs.write_command('r.colors', map=output_name, rules='-',
                     stdin=color_rules, quiet=True)


def set_alteration_colors(output_name):
    """Set color table for alteration type map."""
    color_rules = """\
1 white
2 0:100:0
3 purple
4 148:0:211
5 magenta
6 brown
7 yellow
8 orange
9 135:206:235
10 0:0:139
"""
    gs.write_command('r.colors', map=output_name, rules='-',
                     stdin=color_rules, quiet=True)


def set_family_categories(output_name):
    """Set category labels for rock family map."""
    cats_input = "\n".join(
        f"{k}:{v}" for k, v in ROCK_FAMILY_CLASSES.items()
    )
    gs.write_command('r.category', map=output_name, rules='-',
                     separator=':', stdin=cats_input, quiet=True)


def set_weathering_categories(output_name):
    """Set category labels for weathering map."""
    cats_input = "\n".join(
        f"{k}:{v}" for k, v in WEATHERING_CLASSES.items()
    )
    gs.write_command('r.category', map=output_name, rules='-',
                     separator=':', stdin=cats_input, quiet=True)


def set_alteration_categories(output_name):
    """Set category labels for alteration map."""
    cats_input = "\n".join(
        f"{k}:{v}" for k, v in ALTERATION_CLASSES.items()
    )
    gs.write_command('r.category', map=output_name, rules='-',
                     separator=':', stdin=cats_input, quiet=True)


def set_map_metadata(output_name, title, description):
    """Set raster map title and description via r.support."""
    try:
        gs.run_command('r.support', map=output_name,
                       title=title,
                       description=description,
                       quiet=True)
    except Exception as e:
        gs.warning(f"Could not set metadata for {output_name}: {e}")


# ---------------------------------------------------------------------------
# Mineral indicator output maps
# ---------------------------------------------------------------------------

def output_mineral_maps(indicators, prefix, tmp_maps):
    """Copy indicator maps to user-visible output maps with given prefix."""
    mineral_keys = [
        'jarosite_vnir', 'hematite_vnir', 'goethite_900', 'fe_oxide_broad',
        'ferrous_1000', 'hydroxyl_1400', 'water_1900', 'aloh_2200',
        'aloh_position', 'mgoh_2300', 'carbonate_2340', 'gypsum_1750',
        'alunite_2270', 'reactivity_index', 'clay_mixture_index',
    ]
    for key in mineral_keys:
        src = indicators.get(key)
        if src is None:
            continue
        dst = f"{prefix}_{key}"
        try:
            gs.run_command('r.mapcalc',
                           expression=f"{dst} = {src}",
                           overwrite=True, quiet=True)
            gs.message(f"    Wrote mineral indicator: {dst}")
        except Exception as e:
            gs.warning(f"Could not write mineral map {dst}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(options, flags):
    raster3d = options['input']
    output_family = options['output_family']
    output_weathering = options.get('output_weathering') or ''
    output_alteration = options.get('output_alteration') or ''
    output_prefix = options.get('output_prefix') or ''
    min_wl = float(options['min_wavelength']) if options.get('min_wavelength') else None
    max_wl = float(options['max_wavelength']) if options.get('max_wavelength') else None

    flag_n = flags.get('n', False)
    flag_m = flags.get('m', False)
    flag_i = flags.get('i', False)
    flag_v = flags.get('v', False)

    if flag_m and not output_prefix:
        gs.fatal("Flag -m requires output_prefix to be specified")

    pid = os.getpid()
    tmp_maps = []

    # ------------------------------------------------------------------
    # Step 1: Scan bands
    # ------------------------------------------------------------------
    gs.message(f"Scanning hyperspectral bands in: {raster3d}")
    bands = get_all_band_wavelengths(raster3d, only_valid=flag_n,
                                     min_wl=min_wl, max_wl=max_wl)
    if bands and bands[0]['map_name'] is None:
        extract_band_slices(raster3d, bands, pid, tmp_maps)
    cov = assess_coverage(bands)

    gs.message(f"Found {cov['n_total']} usable bands: "
               f"{cov['wl_min']:.1f} - {cov['wl_max']:.1f} nm")

    # Warn about missing spectral regions
    if not cov['has_vnir']:
        gs.warning("VNIR (400-1000 nm) not covered - Fe-oxide and Fe2+ detection disabled")
    if not cov['has_swir_aloh']:
        gs.warning("SWIR Al-OH region (2100-2300 nm) not covered - clay/mica detection disabled")
    if not cov['has_swir_mgoh']:
        gs.warning("SWIR Mg-OH region (2250-2400 nm) not covered - chlorite/serpentine detection disabled")
    if not cov['has_swir_co3']:
        gs.warning("SWIR CO3 region (2290-2400 nm) not covered - carbonate detection disabled")

    # ------------------------------------------------------------------
    # Info mode
    # ------------------------------------------------------------------
    if flag_i:
        print_info(bands, cov)
        return 0

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    try:
        # Step 2-3: Compute spectral indicators
        gs.message("Step 1/4: Computing spectral indicators...")
        gs.percent(0, 4, 1)
        indicators = compute_all_indicators(raster3d, bands, pid, tmp_maps,
                                            verbose=flag_v)

        # Step 4: Rock family classification
        gs.message("Step 2/4: Building rock family classification scores...")
        gs.percent(1, 4, 1)
        scores = build_class_scores(pid, indicators, tmp_maps, verbose=flag_v)

        gs.message(f"  Writing rock family map: {output_family}")
        build_family_classification(pid, indicators, scores, tmp_maps, output_family)
        set_family_colors(output_family)
        set_family_categories(output_family)
        set_map_metadata(output_family,
                         title="Rock family classification",
                         description=(f"Geological rock family classification from {raster3d}. "
                                      "Classes: 0=Masked, 1=Mafic, 2=Ultramafic, 3=Felsic, "
                                      "4=Intermediate, 5=Carbonate, 6=Siliciclastic, "
                                      "7=Metamorphic, 8=Evaporite, 9=Uncertain"))

        # Step 5: Weathering grade
        if output_weathering:
            gs.message("Step 3/4: Building weathering grade map...")
            gs.percent(2, 4, 1)
            gs.message(f"  Writing weathering map: {output_weathering}")
            build_weathering_map(pid, indicators, output_weathering)
            set_weathering_colors(output_weathering)
            set_weathering_categories(output_weathering)
            set_map_metadata(output_weathering,
                             title="Weathering grade W0-W5",
                             description=(f"Spectroscopic weathering grade from {raster3d}. "
                                          "0=W0 Fresh, 1=W1 Slightly, 2=W2 Moderately, "
                                          "3=W3 Highly, 4=W4 Completely, 5=W5 Residual"))
        else:
            gs.percent(2, 4, 1)

        # Step 6: Alteration type
        if output_alteration:
            gs.message("Step 4/4: Building alteration type map...")
            gs.percent(3, 4, 1)
            gs.message(f"  Writing alteration map: {output_alteration}")
            build_alteration_map(pid, indicators, output_alteration)
            set_alteration_colors(output_alteration)
            set_alteration_categories(output_alteration)
            set_map_metadata(output_alteration,
                             title="Hydrothermal/supergene alteration type",
                             description=(f"Alteration type classification from {raster3d}. "
                                          "1=Unaltered, 2=Propylitic, 3=Phyllic, 4=Argillic, "
                                          "5=AdvArgillic, 6=Supergene, 7=AMD-active, "
                                          "8=AMD-mature, 9=Carbonate, 10=Serpentinization"))
        else:
            gs.percent(3, 4, 1)

        # Step 7: Optional mineral indicator maps
        if flag_m:
            gs.message(f"  Writing mineral indicator maps with prefix: {output_prefix}")
            output_mineral_maps(indicators, output_prefix, tmp_maps)

        gs.percent(4, 4, 1)
        gs.message(" ")
        gs.message("=" * 60)
        gs.message("i.hyper.geology completed successfully.")
        gs.message(f"  Rock family map:   {output_family}")
        if output_weathering:
            gs.message(f"  Weathering map:    {output_weathering}")
        if output_alteration:
            gs.message(f"  Alteration map:    {output_alteration}")
        gs.message("=" * 60)

    finally:
        # Always clean up temp maps
        gs.message("Cleaning up temporary maps...")
        remove_tmp_maps(tmp_maps)

    return 0


if __name__ == "__main__":
    options, flags = gs.parser()
    sys.exit(main(options, flags))
