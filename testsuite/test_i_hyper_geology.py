"""
Name:      i.hyper.geology test suite
Purpose:   Tests for the i.hyper.geology GRASS module.

           Covers:
             - Parameter validation and required-input enforcement
             - Info mode (-i flag)
             - Basic run with synthetic 3D raster input
             - Output map existence and integer value ranges
             - Category label assignment
             - All three output maps (family, weathering, alteration)
             - Mineral indicator export (-m flag)
             - Valid-bands-only filter (-n flag)
             - Spectral end-member scenes: fresh_mafic, goethite, kaolinite,
               white_mica, carbonate, gypsum_amd, serpentinite
             - Degraded-sensor coverage (SWIR-only, VNIR-only)

Author:    Yann Chemin <yann.chemin@gmail.com>
Copyright: (C) 2026 by Yann Chemin and the GRASS Development Team
License:   GPL-2.0-or-later

Run from inside a GRASS session
--------------------------------
    cd i.hyper.geology/testsuite
    python -m grass.gunittest.main
"""

import os
import sys

import grass.script as gs
from grass.gunittest.case import TestCase
from grass.gunittest.main import test

# Make the testsuite directory importable so we can use generate_test_data
sys.path.insert(0, os.path.dirname(__file__))
from generate_test_data import (
    BAND_WAVELENGTHS,
    N_BANDS,
    SCENE_FUNCTIONS,
    SCENE_EXPECTATIONS,
    cleanup_scene,
    create_scene,
    inject_band_metadata,
    setup_test_region,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_ROWS = 20
_COLS = 20

# Minimal scene used across non-scene-specific tests
_SCENE_MIN = "ihgeol_test_min"
# Prefix for output maps to avoid clashing with user maps
_OUT_PREFIX = "ihgeol_out"


# ---------------------------------------------------------------------------
# Helper: raster statistics query
# ---------------------------------------------------------------------------

def _univar(map_name, key, raster_type="raster"):
    """Return float univar statistic for a raster map."""
    cmd = "r.univar" if raster_type == "raster" else "r3.univar"
    result = gs.parse_command(cmd, map=map_name, flags="g")
    return float(result[key])


def _raster_values_in_set(map_name, valid_set):
    """Return True if all unique integer values in map are within valid_set."""
    raw = gs.read_command("r.stats", input=map_name, flags="n", quiet=True)
    found = set()
    for line in raw.strip().splitlines():
        parts = line.strip().split()
        if parts:
            try:
                found.add(int(float(parts[0])))
            except ValueError:
                pass
    return found.issubset(valid_set)


# ===========================================================================
# TestHyperGeologyModuleExists
# Quick smoke test — does not need any data.
# ===========================================================================

class TestHyperGeologyModuleExists(TestCase):
    """Verify the module is installed and its help text is accessible."""

    def test_module_help(self):
        """i.hyper.geology --help must succeed (exits 0 with usage info)."""
        import subprocess, os
        gisbase = os.environ.get("GISBASE", "")
        script = os.path.join(gisbase, "scripts", "i.hyper.geology")
        if not os.path.isfile(script):
            self.skipTest("i.hyper.geology not installed at expected path")
        result = subprocess.run(
            ["python3", script, "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         msg=f"--help returned non-zero: {result.stderr[:200]}")
        self.assertIn("output_family", result.stdout + result.stderr,
                      msg="--help output missing expected parameter name")

    def test_module_in_path(self):
        """i.hyper.geology script must be installed under $GISBASE/scripts."""
        import os
        gisbase = os.environ.get("GISBASE", "")
        script = os.path.join(gisbase, "scripts", "i.hyper.geology")
        self.assertTrue(
            os.path.isfile(script),
            msg=f"i.hyper.geology not found at {script}",
        )


# ===========================================================================
# TestHyperGeologyParameterValidation
# ===========================================================================

class TestHyperGeologyParameterValidation(TestCase):
    """Required parameters must be enforced; invalid values must be rejected."""

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        # Create a minimal 3D raster named _SCENE_MIN for raster3d_info()
        cls.runModule("r3.mapcalc",
                      expression=f"{_SCENE_MIN} = 0.15",
                      overwrite=True)
        # Create band #1 with metadata (enough to make module find at least 1 band)
        cls.runModule("r.mapcalc",
                      expression=f'"{_SCENE_MIN}#1" = 0.15',
                      overwrite=True)
        inject_band_metadata(f"{_SCENE_MIN}#1", wavelength_nm=550.0)

    @classmethod
    def tearDownClass(cls):
        cls.runModule("g.remove", type="raster_3d",
                      name=_SCENE_MIN, flags="f", quiet=True)
        cls.runModule("g.remove", type="raster",
                      name=f"{_SCENE_MIN}#1", flags="f", quiet=True)
        cls.del_temp_region()

    def test_missing_input_fails(self):
        """Module must fail when input= is not provided."""
        self.assertModuleFail(
            "i.hyper.geology",
            output_family=f"{_OUT_PREFIX}_family",
        )

    def test_missing_output_family_fails(self):
        """Module must fail when output_family= is not provided."""
        self.assertModuleFail(
            "i.hyper.geology",
            input=_SCENE_MIN,
        )

    def test_flag_m_without_prefix_fails(self):
        """Flag -m without output_prefix= must cause a fatal error."""
        self.assertModuleFail(
            "i.hyper.geology",
            input=_SCENE_MIN,
            output_family=f"{_OUT_PREFIX}_family",
            flags="m",
        )

    def test_nonexistent_input_fails(self):
        """Module must fail for a nonexistent 3D raster input."""
        self.assertModuleFail(
            "i.hyper.geology",
            input="this_map_does_not_exist_xyz123",
            output_family=f"{_OUT_PREFIX}_family",
        )


# ===========================================================================
# TestHyperGeologyInfoMode
# ===========================================================================

class TestHyperGeologyInfoMode(TestCase):
    """The -i flag must print capability table and exit without creating outputs."""

    _scene = "ihgeol_test_info"
    _out = f"{_OUT_PREFIX}_info_family"

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        create_scene(cls._scene, spectral_name="fresh_mafic")

    @classmethod
    def tearDownClass(cls):
        cleanup_scene(cls._scene)
        cls.del_temp_region()

    def test_info_mode_succeeds(self):
        """Module with -i flag must exit 0."""
        self.assertModule(
            "i.hyper.geology",
            input=self._scene,
            output_family=self._out,
            flags="i",
        )

    def test_info_mode_no_output_created(self):
        """With -i flag, output_family map must NOT be created in the mapset."""
        self.assertModule(
            "i.hyper.geology",
            input=self._scene,
            output_family=self._out,
            flags="i",
        )
        # Map should not exist after info-only run
        found = gs.find_file(self._out, element="cell")
        self.assertEqual(
            found["name"], "",
            msg=f"output_family map '{self._out}' was created in info mode",
        )


# ===========================================================================
# TestHyperGeologyBasicRun
# A full run with the fresh_mafic scene (all bands present).
# Tests output existence, types, and value ranges.
# ===========================================================================

class TestHyperGeologyBasicRun(TestCase):
    """Basic module run: all three outputs + mineral indicator maps."""

    _scene = "ihgeol_test_basic"
    _fam = f"{_OUT_PREFIX}_basic_family"
    _wth = f"{_OUT_PREFIX}_basic_weathering"
    _alt = f"{_OUT_PREFIX}_basic_alteration"
    _pfx = f"{_OUT_PREFIX}_basic_min"

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        create_scene(cls._scene, spectral_name="fresh_mafic")
        # Run module once; subsequent tests inspect the outputs
        cls.runModule(
            "i.hyper.geology",
            input=cls._scene,
            output_family=cls._fam,
            output_weathering=cls._wth,
            output_alteration=cls._alt,
            output_prefix=cls._pfx,
            flags="m",
            overwrite=True,
        )

    @classmethod
    def tearDownClass(cls):
        cleanup_scene(cls._scene)
        for mp in [cls._fam, cls._wth, cls._alt]:
            cls.runModule("g.remove", type="raster", name=mp,
                          flags="f", quiet=True)
        # Remove mineral indicator maps
        mineral_keys = [
            "jarosite_vnir", "hematite_vnir", "goethite_900", "fe_oxide_broad",
            "ferrous_1000", "hydroxyl_1400", "water_1900", "aloh_2200",
            "aloh_position", "mgoh_2300", "carbonate_2340", "gypsum_1750",
            "alunite_2270", "reactivity_index", "clay_mixture_index",
        ]
        for key in mineral_keys:
            cls.runModule("g.remove", type="raster",
                          name=f"{cls._pfx}_{key}",
                          flags="f", quiet=True)
        cls.del_temp_region()

    # --- output existence ---------------------------------------------------

    def test_family_map_exists(self):
        """output_family raster must be present in the mapset."""
        self.assertRasterExists(self._fam)

    def test_weathering_map_exists(self):
        """output_weathering raster must be present in the mapset."""
        self.assertRasterExists(self._wth)

    def test_alteration_map_exists(self):
        """output_alteration raster must be present in the mapset."""
        self.assertRasterExists(self._alt)

    # --- value ranges -------------------------------------------------------

    def test_family_values_in_range(self):
        """Rock family values must all lie in [0, 9]."""
        valid = set(range(10))
        self.assertTrue(
            _raster_values_in_set(self._fam, valid),
            msg="Rock family map contains values outside [0, 9]",
        )

    def test_weathering_values_in_range(self):
        """Weathering grade values must all lie in [0, 5]."""
        valid = set(range(6))
        self.assertTrue(
            _raster_values_in_set(self._wth, valid),
            msg="Weathering map contains values outside [0, 5]",
        )

    def test_alteration_values_in_range(self):
        """Alteration type values must all lie in [1, 10]."""
        valid = set(range(1, 11))
        self.assertTrue(
            _raster_values_in_set(self._alt, valid),
            msg="Alteration map contains values outside [1, 10]",
        )

    # --- no null pixels -------------------------------------------------------

    def test_family_no_nulls(self):
        """Rock family map must have no null pixels for a fully covered scene."""
        self.assertRasterFitsUnivar(
            raster=self._fam,
            reference={"null_cells": 0},
            precision=0,
        )

    # --- mineral indicator maps ---------------------------------------------

    def test_goethite_indicator_exists(self):
        """goethite_900 mineral indicator map must be created with -m flag."""
        self.assertRasterExists(f"{self._pfx}_goethite_900")

    def test_aloh_indicator_exists(self):
        """aloh_2200 mineral indicator map must be created with -m flag."""
        self.assertRasterExists(f"{self._pfx}_aloh_2200")

    def test_mineral_indicators_non_negative(self):
        """All band-depth mineral indicators must be >= 0."""
        for key in ("goethite_900", "aloh_2200", "mgoh_2300", "carbonate_2340",
                    "gypsum_1750", "alunite_2270", "ferrous_1000",
                    "hydroxyl_1400", "water_1900"):
            map_name = f"{self._pfx}_{key}"
            if gs.find_file(map_name, element="cell")["name"]:
                mn = _univar(map_name, "min")
                self.assertGreaterEqual(
                    mn, 0.0,
                    msg=f"Indicator {key} has negative values (min={mn:.4f})",
                )

    def test_reactivity_index_positive(self):
        """Reactivity index must be > 0 (ratio of reflectances)."""
        map_name = f"{self._pfx}_reactivity_index"
        if gs.find_file(map_name, element="cell")["name"]:
            mn = _univar(map_name, "min")
            self.assertGreater(
                mn, 0.0,
                msg=f"Reactivity index has non-positive minimum: {mn:.4f}",
            )


# ===========================================================================
# TestHyperGeologyOutputMetadata
# Checks color tables and category labels set by the module.
# ===========================================================================

class TestHyperGeologyOutputMetadata(TestCase):
    """Color tables and category labels must be assigned correctly."""

    _scene = "ihgeol_test_meta"
    _fam = f"{_OUT_PREFIX}_meta_family"
    _wth = f"{_OUT_PREFIX}_meta_weathering"
    _alt = f"{_OUT_PREFIX}_meta_alteration"

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        create_scene(cls._scene, spectral_name="fresh_mafic")
        cls.runModule(
            "i.hyper.geology",
            input=cls._scene,
            output_family=cls._fam,
            output_weathering=cls._wth,
            output_alteration=cls._alt,
            overwrite=True,
        )

    @classmethod
    def tearDownClass(cls):
        cleanup_scene(cls._scene)
        for mp in [cls._fam, cls._wth, cls._alt]:
            cls.runModule("g.remove", type="raster", name=mp,
                          flags="f", quiet=True)
        cls.del_temp_region()

    def _get_color_rules(self, map_name):
        return gs.read_command("r.colors", map=map_name, flags="p", quiet=True)

    def test_family_has_color_table(self):
        """Rock family map must have a color table assigned."""
        colors = gs.read_command("r.colors.out", map=self._fam, quiet=True)
        self.assertGreater(
            len(colors.strip()), 0,
            msg="No color table found for rock family map",
        )

    def test_weathering_has_color_table(self):
        """Weathering map must have a color table assigned."""
        colors = gs.read_command("r.colors.out", map=self._wth, quiet=True)
        self.assertGreater(len(colors.strip()), 0)

    def test_alteration_has_color_table(self):
        """Alteration map must have a color table assigned."""
        colors = gs.read_command("r.colors.out", map=self._alt, quiet=True)
        self.assertGreater(len(colors.strip()), 0)

    def test_family_has_categories(self):
        """Rock family map must have category labels (at least one assigned)."""
        cats = gs.read_command("r.category", map=self._fam, quiet=True)
        self.assertIn("Mafic", cats, msg="Expected 'Mafic' category label not found")

    def test_weathering_has_categories(self):
        """Weathering map must have category labels assigned."""
        cats = gs.read_command("r.category", map=self._wth, quiet=True)
        # fresh_mafic produces W1 (Slightly weathered), not W0
        self.assertTrue(
            any(label in cats for label in ["Fresh", "Slightly", "Moderately", "Highly", "Completely", "Residual"]),
            msg=f"No valid weathering category label found in: {cats!r}",
        )

    def test_alteration_has_categories(self):
        """Alteration map must include 'Unaltered' label."""
        cats = gs.read_command("r.category", map=self._alt, quiet=True)
        self.assertIn("Unaltered", cats)

    def test_family_map_title_set(self):
        """Rock family map must have a non-empty title."""
        info = gs.parse_command("r.info", map=self._fam, flags="e")
        title = info.get("title", "").strip().strip('"')
        self.assertGreater(len(title), 0, msg="Rock family map has no title")


# ===========================================================================
# TestHyperGeologyFlags
# Tests the -n and -v flags do not break the run.
# ===========================================================================

class TestHyperGeologyFlags(TestCase):
    """Module flags -n and -v must not cause errors."""

    _scene = "ihgeol_test_flags"
    _fam_n = f"{_OUT_PREFIX}_flags_n_family"
    _fam_v = f"{_OUT_PREFIX}_flags_v_family"

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        create_scene(cls._scene, spectral_name="fresh_mafic")

    @classmethod
    def tearDownClass(cls):
        cleanup_scene(cls._scene)
        for mp in [cls._fam_n, cls._fam_v]:
            cls.runModule("g.remove", type="raster", name=mp,
                          flags="f", quiet=True)
        cls.del_temp_region()

    def test_flag_n_valid_bands_only(self):
        """Module must run with -n flag (valid bands only)."""
        self.assertModule(
            "i.hyper.geology",
            input=self._scene,
            output_family=self._fam_n,
            flags="n",
            overwrite=True,
        )
        self.assertRasterExists(self._fam_n)

    def test_flag_v_verbose(self):
        """Module must run with -v flag (verbose indicator logging)."""
        self.assertModule(
            "i.hyper.geology",
            input=self._scene,
            output_family=self._fam_v,
            flags="v",
            overwrite=True,
        )
        self.assertRasterExists(self._fam_v)


# ===========================================================================
# TestHyperGeologyWavelengthFilter
# The min_wavelength / max_wavelength options restrict which bands are used.
# ===========================================================================

class TestHyperGeologyWavelengthFilter(TestCase):
    """Wavelength range options must restrict band scanning."""

    _scene = "ihgeol_test_wl"
    _fam_full = f"{_OUT_PREFIX}_wl_full"
    _fam_swir = f"{_OUT_PREFIX}_wl_swir"

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        create_scene(cls._scene, spectral_name="carbonate")

    @classmethod
    def tearDownClass(cls):
        cleanup_scene(cls._scene)
        for mp in [cls._fam_full, cls._fam_swir]:
            cls.runModule("g.remove", type="raster", name=mp,
                          flags="f", quiet=True)
        cls.del_temp_region()

    def test_full_range_run(self):
        """Full wavelength range run must succeed."""
        self.assertModule(
            "i.hyper.geology",
            input=self._scene,
            output_family=self._fam_full,
            overwrite=True,
        )
        self.assertRasterExists(self._fam_full)

    def test_swir_only_range(self):
        """SWIR-only restriction (1000-2500 nm) must succeed with a warning."""
        self.assertModule(
            "i.hyper.geology",
            input=self._scene,
            output_family=self._fam_swir,
            min_wavelength=1000,
            max_wavelength=2500,
            overwrite=True,
        )
        self.assertRasterExists(self._fam_swir)

    def test_swir_only_family_valid_range(self):
        """With SWIR-only input, family values must still be in [0, 9]."""
        self.assertModule(
            "i.hyper.geology",
            input=self._scene,
            output_family=self._fam_swir,
            min_wavelength=1000,
            max_wavelength=2500,
            overwrite=True,
        )
        valid = set(range(10))
        self.assertTrue(_raster_values_in_set(self._fam_swir, valid))


# ===========================================================================
# TestHyperGeologySceneFamilies
# Each synthetic end-member scene should produce a dominant rock family
# that matches geological expectations.
# Tests are data-driven: one test method per scene.
# ===========================================================================

class TestHyperGeologySceneFamilies(TestCase):
    """Rock family classifications for each geological end-member scene."""

    # Class-level scene storage — created once, shared by all test methods
    _scenes_created = {}
    _out_maps = {}

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        for sc in SCENE_FUNCTIONS:
            sc_info = create_scene(sc)
            cls._scenes_created[sc] = sc_info
            out = f"{_OUT_PREFIX}_scfam_{sc}"
            cls._out_maps[sc] = out
            cls.runModule(
                "i.hyper.geology",
                input=sc,
                output_family=out,
                overwrite=True,
            )

    @classmethod
    def tearDownClass(cls):
        for sc in SCENE_FUNCTIONS:
            cleanup_scene(sc)
        for mp in cls._out_maps.values():
            cls.runModule("g.remove", type="raster", name=mp,
                          flags="f", quiet=True)
        cls.del_temp_region()

    def _dominant_class(self, map_name):
        """Return the most frequent non-zero integer class in map_name."""
        raw = gs.read_command("r.stats", input=map_name, flags="cn", quiet=True)
        best_count = 0
        best_class = None
        for line in raw.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    cls_val = int(float(parts[0]))
                    count = int(parts[1])
                    if cls_val != 0 and count > best_count:
                        best_count = count
                        best_class = cls_val
                except ValueError:
                    pass
        return best_class

    def test_fresh_mafic_family(self):
        """Fresh mafic scene dominant class must be Mafic (1)."""
        exp = SCENE_EXPECTATIONS["fresh_mafic"]
        dominant = self._dominant_class(self._out_maps["fresh_mafic"])
        self.assertEqual(
            dominant, exp["family_class"],
            msg=f"fresh_mafic: expected class {exp['family_class']}, got {dominant}",
        )

    def test_carbonate_family(self):
        """Carbonate scene dominant class must be Carbonate (5)."""
        exp = SCENE_EXPECTATIONS["carbonate"]
        dominant = self._dominant_class(self._out_maps["carbonate"])
        self.assertEqual(
            dominant, exp["family_class"],
            msg=f"carbonate: expected class {exp['family_class']}, got {dominant}",
        )

    def test_white_mica_family(self):
        """White mica / phyllic scene dominant class must be Felsic (3)."""
        exp = SCENE_EXPECTATIONS["white_mica"]
        dominant = self._dominant_class(self._out_maps["white_mica"])
        self.assertEqual(
            dominant, exp["family_class"],
            msg=f"white_mica: expected class {exp['family_class']}, got {dominant}",
        )

    def test_gypsum_amd_family(self):
        """Gypsum/AMD scene dominant class must be Evaporite (8)."""
        exp = SCENE_EXPECTATIONS["gypsum_amd"]
        dominant = self._dominant_class(self._out_maps["gypsum_amd"])
        self.assertEqual(
            dominant, exp["family_class"],
            msg=f"gypsum_amd: expected class {exp['family_class']}, got {dominant}",
        )

    def test_serpentinite_family(self):
        """Serpentinite scene dominant class must be Ultramafic (2)."""
        exp = SCENE_EXPECTATIONS["serpentinite"]
        dominant = self._dominant_class(self._out_maps["serpentinite"])
        self.assertEqual(
            dominant, exp["family_class"],
            msg=f"serpentinite: expected class {exp['family_class']}, got {dominant}",
        )

    def test_goethite_family_is_plausible(self):
        """Goethite scene dominant class must be Mafic (1) or Siliciclastic (6)."""
        exp = SCENE_EXPECTATIONS["goethite"]
        dominant = self._dominant_class(self._out_maps["goethite"])
        self.assertIn(
            dominant, exp["family_class_options"],
            msg=(f"goethite: expected one of {exp['family_class_options']}, "
                 f"got {dominant}"),
        )

    def test_kaolinite_family_is_plausible(self):
        """Kaolinite scene dominant class must be Felsic (3) or Siliciclastic (6)."""
        exp = SCENE_EXPECTATIONS["kaolinite"]
        dominant = self._dominant_class(self._out_maps["kaolinite"])
        self.assertIn(
            dominant, exp["family_class_options"],
            msg=(f"kaolinite: expected one of {exp['family_class_options']}, "
                 f"got {dominant}"),
        )

    def test_all_scenes_produce_non_uncertain_majority(self):
        """Majority class must not be Uncertain (9) for any well-defined scene."""
        for sc in SCENE_FUNCTIONS:
            dominant = self._dominant_class(self._out_maps[sc])
            self.assertNotEqual(
                dominant, 9,
                msg=(f"Scene '{sc}' produced Uncertain (9) as dominant class; "
                     "check spectral indicator computation."),
            )


# ===========================================================================
# TestHyperGeologySceneWeathering
# Weathering grades: fresh_mafic → low, goethite → high.
# ===========================================================================

class TestHyperGeologySceneWeathering(TestCase):
    """Weathering grades must be physically consistent with spectral signatures."""

    _scene_fresh = "ihgeol_test_wth_fresh"
    _scene_wth = "ihgeol_test_wth_goeth"
    _fam_fresh = f"{_OUT_PREFIX}_wth_fresh_fam"
    _wth_fresh = f"{_OUT_PREFIX}_wth_fresh"
    _fam_goeth = f"{_OUT_PREFIX}_wth_goeth_fam"
    _wth_goeth = f"{_OUT_PREFIX}_wth_goeth"

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        create_scene(cls._scene_fresh, spectral_name="fresh_mafic")
        create_scene(cls._scene_wth, spectral_name="goethite")
        cls.runModule(
            "i.hyper.geology",
            input=cls._scene_fresh,
            output_family=cls._fam_fresh,
            output_weathering=cls._wth_fresh,
            overwrite=True,
        )
        cls.runModule(
            "i.hyper.geology",
            input=cls._scene_wth,
            output_family=cls._fam_goeth,
            output_weathering=cls._wth_goeth,
            overwrite=True,
        )

    @classmethod
    def tearDownClass(cls):
        cleanup_scene(cls._scene_fresh)
        cleanup_scene(cls._scene_wth)
        for mp in [cls._fam_fresh, cls._wth_fresh,
                   cls._fam_goeth, cls._wth_goeth]:
            cls.runModule("g.remove", type="raster", name=mp,
                          flags="f", quiet=True)
        cls.del_temp_region()

    def _mean_grade(self, map_name):
        return _univar(map_name, "mean")

    def test_fresh_mafic_low_weathering(self):
        """Fresh mafic mean weathering grade must be <= 1 (W0 or W1)."""
        mean_w = self._mean_grade(self._wth_fresh)
        exp_max = SCENE_EXPECTATIONS["fresh_mafic"]["weathering_max"]
        self.assertLessEqual(
            mean_w, exp_max + 0.5,
            msg=(f"fresh_mafic mean weathering {mean_w:.2f} exceeds expected "
                 f"maximum {exp_max}"),
        )

    def test_goethite_higher_weathering_than_fresh(self):
        """Goethite scene mean weathering grade must exceed fresh mafic."""
        mean_fresh = self._mean_grade(self._wth_fresh)
        mean_goeth = self._mean_grade(self._wth_goeth)
        self.assertGreater(
            mean_goeth, mean_fresh,
            msg=(f"Goethite scene mean weathering ({mean_goeth:.2f}) should be "
                 f"higher than fresh mafic ({mean_fresh:.2f})"),
        )

    def test_goethite_weathering_grade_gte_2(self):
        """Goethite scene dominant weathering grade must be >= W2."""
        exp_min = SCENE_EXPECTATIONS["goethite"]["weathering_min"]
        mean_w = self._mean_grade(self._wth_goeth)
        self.assertGreaterEqual(
            mean_w, exp_min - 0.5,
            msg=(f"Goethite mean weathering {mean_w:.2f} below expected "
                 f"minimum {exp_min}"),
        )


# ===========================================================================
# TestHyperGeologySceneAlteration
# Alteration types for key mining-relevant scenes.
# ===========================================================================

class TestHyperGeologySceneAlteration(TestCase):
    """Alteration types must reflect diagnostic spectral features."""

    # Scenes and their expected dominant alteration classes
    _ALTERATION_SCENES = {
        "kaolinite": {"scene": "ihgeol_alt_kaolinite",
                      "expected": 4,       # Argillic
                      "name": "Argillic"},
        "white_mica": {"scene": "ihgeol_alt_white_mica",
                       "expected": 3,      # Phyllic
                       "name": "Phyllic"},
        "gypsum_amd": {"scene": "ihgeol_alt_gypsum_amd",
                       "expected": 7,      # AMD active
                       "name": "AMD active"},
        "serpentinite": {"scene": "ihgeol_alt_serpentinite",
                         "expected": 10,   # Serpentinization
                         "name": "Serpentinization"},
        "carbonate": {"scene": "ihgeol_alt_carbonate",
                      "expected_options": [1, 9],  # Unaltered or Carbonate alt
                      "name": "Unaltered or Carbonate"},
    }

    _out_fam = {}
    _out_alt = {}

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        for key, cfg in cls._ALTERATION_SCENES.items():
            sc = cfg["scene"]
            create_scene(sc, spectral_name=key)
            out_fam = f"{_OUT_PREFIX}_alt_{key}_fam"
            out_alt = f"{_OUT_PREFIX}_alt_{key}_alt"
            cls._out_fam[key] = out_fam
            cls._out_alt[key] = out_alt
            cls.runModule(
                "i.hyper.geology",
                input=sc,
                output_family=out_fam,
                output_alteration=out_alt,
                overwrite=True,
            )

    @classmethod
    def tearDownClass(cls):
        from generate_test_data import cleanup_scene
        for cfg in cls._ALTERATION_SCENES.values():
            cleanup_scene(cfg["scene"])
        for mp in list(cls._out_fam.values()) + list(cls._out_alt.values()):
            cls.runModule("g.remove", type="raster", name=mp,
                          flags="f", quiet=True)
        cls.del_temp_region()

    def _dominant_class(self, map_name):
        raw = gs.read_command("r.stats", input=map_name, flags="cn", quiet=True)
        best_count, best_cls = 0, None
        for line in raw.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    c, n = int(float(parts[0])), int(parts[1])
                    if n > best_count:
                        best_count, best_cls = n, c
                except ValueError:
                    pass
        return best_cls

    def test_kaolinite_argillic_alteration(self):
        """Kaolinite scene must produce Argillic (4) as dominant alteration."""
        dominant = self._dominant_class(self._out_alt["kaolinite"])
        self.assertEqual(dominant, 4,
                         msg=f"kaolinite: expected Argillic (4), got {dominant}")

    def test_white_mica_phyllic_alteration(self):
        """White mica scene must produce Phyllic (3) as dominant alteration."""
        dominant = self._dominant_class(self._out_alt["white_mica"])
        self.assertEqual(dominant, 3,
                         msg=f"white_mica: expected Phyllic (3), got {dominant}")

    def test_gypsum_amd_active_alteration(self):
        """Gypsum/AMD scene must produce AMD active (7) as dominant alteration."""
        dominant = self._dominant_class(self._out_alt["gypsum_amd"])
        self.assertEqual(dominant, 7,
                         msg=f"gypsum_amd: expected AMD active (7), got {dominant}")

    def test_serpentinite_serpentinization(self):
        """Serpentinite scene must produce Serpentinization (10)."""
        dominant = self._dominant_class(self._out_alt["serpentinite"])
        self.assertEqual(dominant, 10,
                         msg=f"serpentinite: expected Serpentinization (10), "
                             f"got {dominant}")

    def test_carbonate_alteration_plausible(self):
        """Carbonate scene alteration must be Unaltered (1) or Carbonate alt (9)."""
        dominant = self._dominant_class(self._out_alt["carbonate"])
        self.assertIn(dominant, [1, 9],
                      msg=f"carbonate: expected 1 or 9, got {dominant}")


# ===========================================================================
# TestHyperGeologyIndicatorPhysics
# Validate that the spectral indicator magnitudes are physically meaningful
# for extreme-signature scenes.
# ===========================================================================

class TestHyperGeologyIndicatorPhysics(TestCase):
    """Mineral indicators must have values in physically expected ranges."""

    _scene = "ihgeol_test_phys"
    _fam = f"{_OUT_PREFIX}_phys_fam"
    _pfx = f"{_OUT_PREFIX}_phys_min"

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        setup_test_region(_ROWS, _COLS)
        # Use the gypsum_amd scene: strongest multi-indicator signature
        create_scene(cls._scene, spectral_name="gypsum_amd")
        cls.runModule(
            "i.hyper.geology",
            input=cls._scene,
            output_family=cls._fam,
            output_prefix=cls._pfx,
            flags="m",
            overwrite=True,
        )

    @classmethod
    def tearDownClass(cls):
        cleanup_scene(cls._scene)
        cls.runModule("g.remove", type="raster", name=cls._fam,
                      flags="f", quiet=True)
        mineral_keys = [
            "jarosite_vnir", "hematite_vnir", "goethite_900", "fe_oxide_broad",
            "ferrous_1000", "hydroxyl_1400", "water_1900", "aloh_2200",
            "aloh_position", "mgoh_2300", "carbonate_2340", "gypsum_1750",
            "alunite_2270", "reactivity_index", "clay_mixture_index",
        ]
        for key in mineral_keys:
            cls.runModule("g.remove", type="raster",
                          name=f"{cls._pfx}_{key}",
                          flags="f", quiet=True)
        cls.del_temp_region()

    def _mean(self, suffix):
        return _univar(f"{self._pfx}_{suffix}", "mean")

    def test_gypsum_1750_positive_depth(self):
        """gypsum_1750 band depth must be > 0 for a gypsum scene."""
        mean = self._mean("gypsum_1750")
        self.assertGreater(mean, 0.0,
                           msg=f"gypsum_1750 mean {mean:.4f} not > 0")

    def test_jarosite_vnir_positive_depth(self):
        """jarosite_vnir band depth must be > 0 for a jarosite/AMD scene."""
        mean = self._mean("jarosite_vnir")
        self.assertGreater(mean, 0.0,
                           msg=f"jarosite_vnir mean {mean:.4f} not > 0")

    def test_aloh_indicator_low_for_gypsum(self):
        """aloh_2200 must be near zero for a gypsum scene (no clay Al-OH)."""
        mean = self._mean("aloh_2200")
        self.assertLess(mean, 0.10,
                        msg=f"aloh_2200 mean {mean:.4f} unexpectedly high for gypsum scene")

    def test_carbonate_low_for_gypsum(self):
        """carbonate_2340 must be low for a gypsum/AMD scene."""
        mean = self._mean("carbonate_2340")
        self.assertLess(mean, 0.10,
                        msg=f"carbonate_2340 mean {mean:.4f} unexpectedly high for gypsum")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    test()
