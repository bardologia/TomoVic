"""Tests covering the shared PlotBase figure helpers.

Covers style application, figure saving, colour limits, normalisation and
subsampling helpers, the image-figure builder, and the paper/report styles.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy             as np
import pytest
from PIL import Image

from tools.reporting.plotting import PlotBase


@pytest.fixture
def plotter():
    """Returns a bare PlotBase instance."""
    return PlotBase()


@pytest.fixture
def small_field():
    """Returns a 24x24 float32 field of standard normal samples."""
    rng = np.random.default_rng(0)
    return rng.normal(size=(24, 24)).astype(np.float32)


def test_apply_style_sets_dpi(plotter):
    """Verifies applying the style pushes the instance DPI into the matplotlib rc parameters."""
    plotter._apply_style()
    assert plt.rcParams["figure.dpi"]  == PlotBase.fig_dpi
    assert plt.rcParams["savefig.dpi"] == PlotBase.save_dpi


def test_apply_style_sets_font_family(plotter):
    """Verifies the style selects a serif font family."""
    plotter._apply_style()
    assert "serif" in plt.rcParams["font.family"]


def test_save_creates_file(plotter, tmp_path):
    """Verifies saving creates missing parent directories and writes a non-empty file."""
    fig = plt.figure()
    fig.add_subplot(111).plot([0, 1], [0, 1])
    out = plotter._save(fig, tmp_path / "deep" / "fig.png")

    assert out.exists()
    assert out.stat().st_size > 0


def test_save_returns_path(plotter, tmp_path):
    """Verifies save returns the path it wrote to."""
    fig = plt.figure()
    out = plotter._save(fig, tmp_path / "x.png")
    assert out == tmp_path / "x.png"


def test_save_closes_figure(plotter, tmp_path):
    """Verifies save closes the figure it wrote."""
    fig = plt.figure()
    num = fig.number
    plotter._save(fig, tmp_path / "y.png")
    assert not plt.fignum_exists(num)


def test_shared_clim_basic():
    """Verifies the shared colour limits are the requested percentiles of the data."""
    arr = np.linspace(0.0, 100.0, 1000).astype(np.float32)
    lo, hi = PlotBase._shared_clim(arr, q_low=1.0, q_high=99.0)
    assert lo < hi
    assert lo == pytest.approx(np.percentile(arr, 1.0))
    assert hi == pytest.approx(np.percentile(arr, 99.0))


def test_shared_clim_ignores_nan():
    """Verifies NaN samples are excluded from the percentile computation."""
    arr = np.array([1.0, 2.0, 3.0, np.nan, 4.0], dtype=np.float32)
    lo, hi = PlotBase._shared_clim(arr, q_low=0.0, q_high=100.0)
    assert lo == pytest.approx(1.0)
    assert hi == pytest.approx(4.0)


def test_shared_clim_multiple_arrays():
    """Verifies limits span the pooled samples of several arrays."""
    a = np.array([0.0, 1.0])
    b = np.array([5.0, 10.0])
    lo, hi = PlotBase._shared_clim(a, b, q_low=0.0, q_high=100.0)
    assert lo == pytest.approx(0.0)
    assert hi == pytest.approx(10.0)


def test_shared_clim_all_nan_raises():
    """Verifies an all-NaN array raises ValueError."""
    arr = np.full(10, np.nan)
    with pytest.raises(ValueError):
        PlotBase._shared_clim(arr)


def test_shared_clim_empty_raises():
    """Verifies an empty array raises ValueError."""
    with pytest.raises(ValueError):
        PlotBase._shared_clim(np.array([]))


def test_cmap_with_bad_returns_colormap():
    """Verifies the helper returns a matplotlib colormap."""
    cmap = PlotBase._cmap_with_bad("viridis")
    assert isinstance(cmap, mcolors.Colormap)


def test_cmap_with_bad_sets_bad_color():
    """Verifies the requested colour is used for masked or non-finite samples."""
    cmap = PlotBase._cmap_with_bad("viridis", bad_color="red")
    bad  = cmap.get_bad()
    assert tuple(bad) == mcolors.to_rgba("red")


def test_amplitude_clim_is_three_times_mean():
    """Verifies amplitude limits run from zero to three times the mean."""
    arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    lo, hi = PlotBase._amplitude_clim(arr)
    assert lo == 0.0
    assert hi == pytest.approx(6.0)


def test_amplitude_clim_ignores_nonfinite():
    """Verifies NaN and infinite samples are excluded from the amplitude mean."""
    arr = np.array([1.0, 3.0, np.nan, np.inf], dtype=np.float32)
    lo, hi = PlotBase._amplitude_clim(arr)
    assert lo == 0.0
    assert hi == pytest.approx(6.0)


def test_amplitude_clim_multiple_arrays():
    """Verifies the amplitude mean pools the samples of several arrays."""
    a = np.array([1.0, 1.0])
    b = np.array([3.0, 3.0])
    lo, hi = PlotBase._amplitude_clim(a, b)
    assert hi == pytest.approx(6.0)


def test_amplitude_clim_empty_raises():
    """Verifies an empty array raises ValueError."""
    with pytest.raises(ValueError):
        PlotBase._amplitude_clim(np.array([]))


def test_amplitude_clim_zero_field_raises():
    """Verifies an all-zero field raises ValueError instead of a degenerate range."""
    with pytest.raises(ValueError):
        PlotBase._amplitude_clim(np.zeros(16, dtype=np.float32))


def test_normalize_01_range():
    """Verifies normalisation maps the field onto [0, 1] in float32."""
    arr  = np.array([2.0, 4.0, 6.0], dtype=np.float32)
    norm = PlotBase._normalize_01(arr)
    assert float(norm.min()) == pytest.approx(0.0)
    assert float(norm.max()) == pytest.approx(1.0)
    assert norm.dtype == np.float32


def test_normalize_01_ignores_nan_for_bounds():
    """Verifies NaN samples do not affect the normalisation bounds."""
    arr  = np.array([0.0, np.nan, 10.0], dtype=np.float32)
    norm = PlotBase._normalize_01(arr)
    assert float(np.nanmax(norm)) == pytest.approx(1.0)


def test_normalize_01_constant_raises():
    """Verifies a constant field raises ValueError."""
    arr = np.full(5, 3.0, dtype=np.float32)
    with pytest.raises(ValueError):
        PlotBase._normalize_01(arr)


def test_subsample_below_max_unchanged():
    """Verifies a field below the cap keeps all its samples."""
    arr = np.arange(10.0)
    out = PlotBase._subsample(arr, n_max=100)
    assert out.size == 10


def test_subsample_above_max_truncates():
    """Verifies a field above the cap is reduced to exactly n_max samples."""
    arr = np.arange(1000.0)
    out = PlotBase._subsample(arr, n_max=50)
    assert out.size == 50


def test_subsample_drops_nan():
    """Verifies non-finite samples are dropped before subsampling."""
    arr = np.array([1.0, np.nan, 2.0, np.nan])
    out = PlotBase._subsample(arr, n_max=100)
    assert out.size == 2
    assert np.all(np.isfinite(out))


def test_subsample_deterministic_seed():
    """Verifies the same seed yields the same subsample."""
    arr = np.arange(1000.0)
    a   = PlotBase._subsample(arr, n_max=20, seed=7)
    b   = PlotBase._subsample(arr, n_max=20, seed=7)
    assert np.array_equal(a, b)


def test_paired_subsample_aligns_finite_mask():
    """Verifies paired subsampling keeps only positions finite in both arrays."""
    a = np.array([1.0, np.nan, 3.0, 4.0])
    b = np.array([10.0, 20.0, np.nan, 40.0])
    out_a, out_b = PlotBase._paired_subsample([a, b], n_max=100)
    assert out_a.size == out_b.size == 2
    assert np.array_equal(out_a, [1.0, 4.0])
    assert np.array_equal(out_b, [10.0, 40.0])


def test_paired_subsample_truncates_to_n_max():
    """Verifies paired subsampling truncates both arrays to the same n_max length."""
    a = np.arange(500.0)
    b = np.arange(500.0)
    out_a, out_b = PlotBase._paired_subsample([a, b], n_max=30)
    assert out_a.size == out_b.size == 30


def test_binned_median_shapes():
    """Verifies the binned median returns one centre and one median per bin."""
    x = np.linspace(0.0, 1.0, 5000)
    y = 2.0 * x
    centers, medians = PlotBase._binned_median(x, y, n_bins=10, min_count=10)
    assert centers.shape == (10,)
    assert medians.shape == (10,)


def test_binned_median_tracks_signal():
    """Verifies the binned medians follow a linear relation between the two variables."""
    x = np.linspace(0.0, 1.0, 5000)
    y = 3.0 * x
    centers, medians = PlotBase._binned_median(x, y, n_bins=10, min_count=10)
    valid = np.isfinite(medians)
    assert np.allclose(medians[valid], 3.0 * centers[valid], atol=0.1)


def test_binned_median_sparse_bins_nan():
    """Verifies bins below the minimum count yield NaN medians."""
    x = np.linspace(0.0, 1.0, 20)
    y = x.copy()
    centers, medians = PlotBase._binned_median(x, y, n_bins=10, min_count=1000)
    assert np.all(np.isnan(medians))


def test_imshow_figure_returns_figure(plotter, small_field):
    """Verifies the image-figure builder returns a matplotlib figure when no path is given."""
    fig = plotter._imshow_figure(
        small_field,
        x_label = "range",
        y_label = "azimuth",
        title   = "field",
        cmap    = "viridis",
    )
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_imshow_figure_axis_labels(plotter, small_field):
    """Verifies the axis labels and title reach the rendered axes."""
    fig = plotter._imshow_figure(
        small_field,
        x_label = "range [m]",
        y_label = "azimuth [m]",
        title   = "Field Title",
        cmap    = "viridis",
    )
    ax = fig.axes[0]
    assert ax.get_xlabel() == "range [m]"
    assert ax.get_ylabel() == "azimuth [m]"
    assert ax.get_title()  == "Field Title"
    plt.close(fig)


def test_imshow_figure_has_colorbar(plotter, small_field):
    """Verifies the figure carries a colorbar axis in addition to the image axis."""
    fig = plotter._imshow_figure(
        small_field,
        x_label = "x",
        y_label = "y",
        title   = "t",
        cmap    = "viridis",
    )
    assert len(fig.axes) >= 2
    plt.close(fig)


def test_imshow_figure_text_overlay(plotter, small_field):
    """Verifies the text overlay is drawn onto the image axis."""
    fig = plotter._imshow_figure(
        small_field,
        x_label      = "x",
        y_label      = "y",
        title        = "t",
        cmap         = "viridis",
        text_overlay = "RMSE=0.1",
    )
    ax    = fig.axes[0]
    texts = [t.get_text() for t in ax.texts]
    assert "RMSE=0.1" in texts
    plt.close(fig)


def test_imshow_figure_discrete_levels(plotter):
    """Verifies a discrete colormap with explicit levels renders a figure."""
    label = np.array([[0, 1, 2], [2, 1, 0], [1, 1, 2]])
    fig   = plotter._imshow_figure(
        label.astype(float),
        x_label  = "x",
        y_label  = "y",
        title    = "labels",
        cmap     = "tab10",
        discrete = True,
        levels   = [0, 1, 2],
    )
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_imshow_figure_saves_to_path(plotter, small_field, tmp_path):
    """Verifies passing a path saves the figure and returns that path."""
    out = plotter._imshow_figure(
        small_field,
        x_label = "x",
        y_label = "y",
        title   = "t",
        cmap    = "viridis",
        path    = tmp_path / "img.png",
    )
    assert out == tmp_path / "img.png"
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.slow
def test_imshow_figure_saved_dpi(plotter, small_field, tmp_path):
    """Verifies the written PNG carries the configured save DPI."""
    out = plotter._imshow_figure(
        small_field,
        x_label = "x",
        y_label = "y",
        title   = "t",
        cmap    = "viridis",
        figsize = (6.0, 4.0),
        path    = tmp_path / "dpi.png",
    )
    with Image.open(out) as img:
        dpi = img.info.get("dpi")
    assert dpi is not None
    assert round(dpi[0]) == PlotBase.save_dpi


@pytest.mark.real_data
@pytest.mark.slow
def test_imshow_real_dem_window(plotter, dem_full, small_window, tmp_path):
    """Verifies a real DEM window renders and saves with a terrain colormap."""
    window = np.asarray(dem_full[small_window], dtype=np.float32)
    out    = plotter._imshow_figure(
        window,
        x_label        = "range",
        y_label        = "azimuth",
        title          = "DEM window",
        cmap           = plotter._cmap_with_bad("terrain"),
        colorbar_label = "height [m]",
        path           = tmp_path / "dem.png",
    )
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.real_data
def test_shared_clim_real_tomogram_intensity(tomogram_full, small_window):
    """Verifies percentile colour limits on a real tomogram layer are finite and ordered."""
    layer = np.abs(np.asarray(tomogram_full[0][small_window]))
    lo, hi = PlotBase._shared_clim(layer, q_low=5.0, q_high=95.0)
    assert lo <= hi
    assert np.isfinite(lo) and np.isfinite(hi)


@pytest.fixture
def paper_style():
    """Switches PlotBase to the paper style for the test and restores the report style afterwards."""
    PlotBase.use_style("paper")
    yield
    PlotBase.use_style("report")


def test_default_style_is_report():
    """Verifies the default figure style is the report style."""
    assert PlotBase.style == "report"


def test_use_style_rejects_unknown():
    """Verifies an unknown style name raises ValueError and leaves the style unchanged."""
    with pytest.raises(ValueError, match="unknown figure style"):
        PlotBase.use_style("poster")
    assert PlotBase.style == "report"


def test_paper_style_sets_print_font_sizes(plotter, paper_style):
    """Verifies the paper style sets the print-sized font, label, tick and legend sizes."""
    plotter._apply_style()
    assert plt.rcParams["font.size"]       == 9
    assert plt.rcParams["axes.labelsize"]  == 9
    assert plt.rcParams["xtick.labelsize"] == 8
    assert plt.rcParams["legend.fontsize"] == 8


def test_paper_style_sets_stix_mathtext(plotter, paper_style):
    """Verifies the paper style selects the STIX mathtext font set."""
    plotter._apply_style()
    assert plt.rcParams["mathtext.fontset"] == "stix"


def test_paper_style_sets_okabe_ito_cycle(plotter, paper_style):
    """Verifies the paper style installs the Okabe-Ito colour cycle."""
    plotter._apply_style()
    assert plt.rcParams["axes.prop_cycle"].by_key()["color"] == PlotBase.OKABE_ITO


def test_paper_style_overrides_instance_dpi(plotter, paper_style):
    """Verifies the paper style forces the print DPI over the instance setting."""
    plotter.fig_dpi  = 150
    plotter.save_dpi = 150
    plotter._apply_style()
    assert plt.rcParams["figure.dpi"]  == PlotBase.PAPER_DPI
    assert plt.rcParams["savefig.dpi"] == PlotBase.PAPER_DPI


def test_paper_style_keeps_scientific_base(plotter, paper_style):
    """Verifies the paper style keeps embedded PDF fonts and the serif family."""
    plotter._apply_style()
    assert plt.rcParams["pdf.fonttype"] == 42
    assert "serif" in plt.rcParams["font.family"]


def test_report_style_restores_after_paper(plotter):
    """Verifies switching back to the report style restores fonts, DPI and colour cycle."""
    PlotBase.use_style("paper")
    plotter._apply_style()
    PlotBase.use_style("report")
    plotter._apply_style()

    assert plt.rcParams["font.size"]        == 11
    assert plt.rcParams["mathtext.fontset"] == "dejavuserif"
    assert plt.rcParams["figure.dpi"]       == plotter.fig_dpi
    assert plt.rcParams["axes.prop_cycle"]  == plt.rcParamsDefault["axes.prop_cycle"]


def test_figsize_full_width():
    """Verifies the full-width figure size uses the default aspect ratio."""
    w, h = PlotBase.figsize(PlotBase.FULL_WIDTH)
    assert w == pytest.approx(5.5)
    assert h == pytest.approx(5.5 * 0.62)


def test_figsize_custom_aspect():
    """Verifies a custom aspect ratio scales the height of a half-width figure."""
    w, h = PlotBase.figsize(PlotBase.HALF_WIDTH, aspect=1.0)
    assert w == pytest.approx(2.65)
    assert h == pytest.approx(2.65)


def test_paper_save_upgrades_line_plot_to_pdf(plotter, paper_style, tmp_path):
    """Verifies the paper style saves a line plot as vector PDF instead of PNG."""
    fig = plt.figure()
    fig.add_subplot(111).plot([0, 1], [0, 1])
    out = plotter._save(fig, tmp_path / "line.png")

    assert out == tmp_path / "line.pdf"
    assert out.read_bytes()[:5] == b"%PDF-"


def test_paper_save_keeps_png_for_images(plotter, paper_style, small_field, tmp_path):
    """Verifies the paper style keeps raster PNG output for image plots."""
    fig = plt.figure()
    fig.add_subplot(111).imshow(small_field)
    out = plotter._save(fig, tmp_path / "map.png")

    assert out == tmp_path / "map.png"
    with Image.open(out) as img:
        assert img.format == "PNG"


def test_paper_save_respects_explicit_pdf(plotter, paper_style, tmp_path):
    """Verifies an explicit .pdf path is written as PDF under the paper style."""
    fig = plt.figure()
    fig.add_subplot(111).plot([0, 1], [0, 1])
    out = plotter._save(fig, tmp_path / "fig.pdf")
    assert out.read_bytes()[:5] == b"%PDF-"


def test_report_save_keeps_png(plotter, tmp_path):
    """Verifies the report style writes line plots as PNG."""
    fig = plt.figure()
    fig.add_subplot(111).plot([0, 1], [0, 1])
    out = plotter._save(fig, tmp_path / "line.png")

    assert out == tmp_path / "line.png"
    with Image.open(out) as img:
        assert img.format == "PNG"
