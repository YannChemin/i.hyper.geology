# Installation — i.hyper.geology

## Prerequisites

| Requirement | Minimum version | Notes |
|-------------|----------------|-------|
| GRASS GIS | 8.2 | 8.4+ recommended |
| Python | 3.8 | Bundled with GRASS on most platforms |
| GRASS Python scripting library | (bundled with GRASS) | `grass.script` |

No additional Python packages are required — all computation is delegated to
GRASS raster tools (`r.mapcalc`, `r.colors`, `r.category`, `r.support`).

---

## Option A — Install via `g.extension` (recommended)

If the module has been published to the GRASS GIS Addons repository:

```bash
# Start GRASS GIS and open a mapset, then:
g.extension extension=i.hyper.geology
```

To install from a local source tree (e.g., during development):

```bash
g.extension extension=i.hyper.geology \
             url=/home/yann/dev/i.hyper.geology
```

`g.extension` compiles, installs the script and HTML manual page, and
registers the module so it appears in the GRASS module search.

---

## Option B — Manual installation from source

### 1. Clone or copy the source

```bash
# If the full i.hyper suite is in a repository:
git clone <repository-url> ~/dev/i.hyper
cd ~/dev/i.hyper.geology

# Or simply copy the directory to a working location.
```

### 2. Set the GRASS build environment

The Makefile assumes a standard GRASS source tree layout.  Point
`MODULE_TOPDIR` to the root of your GRASS installation or build tree:

```bash
# Using an installed GRASS (find the correct path with `grass --config path`):
GRASS_PREFIX=$(grass --config path)
export MODULE_TOPDIR=${GRASS_PREFIX}
```

If you are building against a GRASS source tree (developers):

```bash
export MODULE_TOPDIR=/path/to/grass-source-tree
```

### 3. Compile and install

```bash
cd /home/yann/dev/i.hyper.geology
make MODULE_TOPDIR=${MODULE_TOPDIR}
make install MODULE_TOPDIR=${MODULE_TOPDIR}
```

This installs:

| File | Destination |
|------|-------------|
| `i.hyper.geology.py` | `$GISBASE/scripts/i.hyper.geology` |
| `i.hyper.geology.html` | `$GISBASE/docs/html/i.hyper.geology.html` |

### 4. Verify installation

Start GRASS GIS and run:

```bash
i.hyper.geology --help
```

Expected output begins:

```
Description:
 Geological rock family classification, weathering grade and alteration
 type mapping from hyperspectral imagery

Usage:
 i.hyper.geology [-nmiv] input=name output_family=name
   [output_weathering=name] [output_alteration=name]
   [output_prefix=string] [min_wavelength=float] [max_wavelength=float]
   [--overwrite] [--help] [--verbose] [--quiet] [--ui]
```

---

## Option C — Run directly without installing

For quick testing, execute the script directly from the source directory
inside an active GRASS session:

```bash
# Inside a GRASS terminal session:
python3 /home/yann/dev/i.hyper.geology/i.hyper.geology.py \
        input=my_hyperspectral_cube \
        output_family=rock_family \
        -i
```

---

## Installing the full i.hyper suite

`i.hyper.geology` depends on data imported by `i.hyper.import`.  To install
all modules that are part of the i.hyper family, run `make install` from each
module's directory, or use `g.extension` for each one individually.

Recommended installation order for a complete hyperspectral workflow:

```
i.hyper.import        ← required first (creates 3D raster input format)
i.hyper.atcorr        ← or i.hyper.smac  (atmospheric correction)
i.hyper.specresamp    ← spectral resampling to sensor SRF
i.hyper.continuum     ← continuum removal (improves geology results)
i.hyper.geology       ← this module
i.hyper.indices       ← supplementary spectral indices
i.hyper.albedo        ← broadband albedo
i.hyper.rgb           ← RGB composites for visualisation
```

---

## Troubleshooting

### `No wavelength metadata found`

`i.hyper.geology` reads wavelength metadata from band-slice raster history
set by `i.hyper.import`.  If you see this error, the input was not created
by `i.hyper.import` or is missing `wavelength=`, `FWHM=`, and `valid=` keys
in its band metadata.  Verify with:

```bash
r.info -h map="my_cube#1"
```

The output should include lines such as `wavelength=450.0`, `FWHM=10.0`,
`valid=1`, and `unit=nm` in the history/description section.

### `r.mapcalc` expression too long

On very wide sensors (> 500 bands), the classification expression can exceed
shell limits.  Use the `-n` flag to restrict to valid bands only, which
typically reduces band count by 10–20 %.

### Missing SWIR or VNIR warning

If the sensor does not cover a spectral region (e.g., WV3-SWIR has no VNIR),
`i.hyper.geology` prints a warning and continues with reduced indicator set.
Use `-i` first to inspect which capabilities are available for your sensor:

```bash
i.hyper.geology input=my_cube output_family=dummy -i
```

### Permissions error during `make install`

If you do not have write access to `$GISBASE`, install into a user-writeable
addon directory:

```bash
export GRASS_ADDON_PATH=$HOME/.grass8/addons
make install MODULE_TOPDIR=${MODULE_TOPDIR} \
             INST_DIR=${GRASS_ADDON_PATH}
```

Then add `GRASS_ADDON_PATH` to your shell environment permanently.

---

## Uninstalling

```bash
# Via g.extension:
g.extension extension=i.hyper.geology operation=remove

# Manually:
rm -f ${GISBASE}/scripts/i.hyper.geology
rm -f ${GISBASE}/docs/html/i.hyper.geology.html
```
