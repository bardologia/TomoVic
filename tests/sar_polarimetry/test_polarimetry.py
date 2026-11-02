"""Tests for the Pauli decomposition tools.

Covers the loader channel ordering in its two cross-polar forms, the Pauli
vector identities, multilooked powers, span conservation of the Pauli powers
built from the raw channels, the co-polar powers, the no-data mask, fractions,
dominant mechanism, colour stretch bounds and the RGB composite channel mapping.
"""

from __future__ import annotations

import numpy as np
import pytest

from scipy.ndimage import uniform_filter

from tools.sar.polarimetry import ChannelOrdering, PauliDecomposer, PolarimetricArtifact


def _channels(rng: np.random.Generator, count: int, shape: tuple = (6, 5)) -> np.ndarray:
    """Returns a random complex stack of ``count`` channels."""
    return (rng.normal(size=(count,) + shape) + 1j * rng.normal(size=(count,) + shape)).astype(np.complex64)


def _reciprocal_cross(labels: list, stack: np.ndarray) -> np.ndarray:
    """Returns the reciprocal S_HV a loader stack implies: the mean of HV and VH, or HV alone."""
    if "vh" in labels:
        return (stack[labels.index("hv")] + stack[labels.index("vh")]) / 2.0
    return stack[labels.index("hv")]


def test_ordering_symmetrises_separate_hv_and_vh():
    """Checks HV and VH are averaged as (HV + VH) / sqrt 2 and the co-polar channels keep their place."""
    rng   = np.random.default_rng(1)
    stack = _channels(rng, 4)

    ordering  = ChannelOrdering(["VV", "hv", "VH", "hh"])
    canonical = ordering.canonical(stack)

    assert ordering.cross_source == "hv+vh"
    assert ordering.symmetrised
    assert canonical.dtype == np.complex64
    np.testing.assert_allclose(canonical[0], stack[3])
    np.testing.assert_allclose(canonical[1], (stack[1] + stack[2]) / np.sqrt(2.0), rtol=1e-6)
    np.testing.assert_allclose(canonical[2], stack[0])


def test_ordering_scales_lone_hv_by_sqrt_two():
    """Checks a lone HV channel is scaled to the Pauli cross-polar component."""
    rng   = np.random.default_rng(2)
    stack = _channels(rng, 3)

    ordering  = ChannelOrdering(["hh", "hv", "vv"])
    canonical = ordering.canonical(stack)

    assert ordering.cross_source == "hv"
    assert not ordering.symmetrised
    np.testing.assert_allclose(canonical[1], stack[1] * PolarimetricArtifact.CROSS_SCALE, rtol=1e-6)


@pytest.mark.parametrize("labels", [["hv", "vv"], ["hh", "hh", "hv", "vv"], ["hh", "vv"], ["hh", "vh", "vv"], ["hh", "xx", "vv"], ["hh", "hv", "vh", "vh", "vv"]])
def test_ordering_rejects_incomplete_stacks(labels):
    """Checks missing, repeated, already-symmetrised or VH-only label sets are refused."""
    with pytest.raises(ValueError):
        ChannelOrdering(labels)


def test_ordering_rejects_shape_mismatch():
    """Checks a stack whose channel count differs from the labels is refused."""
    rng = np.random.default_rng(3)

    with pytest.raises(ValueError):
        ChannelOrdering(["hh", "hv", "vv"]).canonical(_channels(rng, 4))


def test_vector_identities():
    """Checks equal co-polar channels cancel the double-bounce term and opposite ones cancel the surface term."""
    rng   = np.random.default_rng(4)
    hh    = _channels(rng, 1)[0]
    cross = _channels(rng, 1)[0]

    equal    = PauliDecomposer.vector(np.stack([hh, cross, hh]))
    opposite = PauliDecomposer.vector(np.stack([hh, cross, -hh]))

    np.testing.assert_allclose(equal[0], np.sqrt(2.0) * hh, rtol=1e-5)
    np.testing.assert_allclose(equal[1], 0.0, atol=1e-6)
    np.testing.assert_allclose(equal[2], cross)
    np.testing.assert_allclose(opposite[0], 0.0, atol=1e-6)
    np.testing.assert_allclose(opposite[1], np.sqrt(2.0) * hh, rtol=1e-5)


def test_vector_rejects_wrong_channel_count():
    """Checks a stack without exactly three channels is refused."""
    rng = np.random.default_rng(5)

    with pytest.raises(ValueError):
        PauliDecomposer.vector(_channels(rng, 4))


def test_powers_single_look_and_multilooked():
    """Checks a unit window returns squared magnitudes and a larger window their boxcar mean."""
    rng   = np.random.default_rng(6)
    stack = _channels(rng, 3, shape=(9, 7))

    single   = PauliDecomposer((1, 1)).powers(stack)
    looked   = PauliDecomposer((3, 3)).powers(stack)
    expected = np.abs(PauliDecomposer.vector(stack)) ** 2

    assert single.dtype == np.float32
    np.testing.assert_allclose(single, expected, rtol=1e-5)
    for index in range(3):
        np.testing.assert_allclose(looked[index], uniform_filter(expected[index].astype(np.float32), (3, 3)), rtol=1e-4)


@pytest.mark.parametrize("labels", [["hh", "hv", "vh", "vv"], ["hh", "hv", "vv"]])
@pytest.mark.parametrize("window", [(1, 1), (3, 2)])
def test_powers_conserve_span_from_loader_stack(labels, window):
    """Checks the Pauli powers sum to |HH|^2 + 2|S_HV|^2 + |VV|^2 and the volume power is 2|S_HV|^2, built from the raw channels only."""
    rng   = np.random.default_rng(7)
    stack = _channels(rng, len(labels), shape=(9, 7))

    powers = PauliDecomposer(window).powers(ChannelOrdering(labels).canonical(stack))

    cross  = _reciprocal_cross(labels, stack)
    volume = uniform_filter((2.0 * np.abs(cross) ** 2).astype(np.float32), window)
    span   = uniform_filter((np.abs(stack[labels.index("hh")]) ** 2 + np.abs(stack[labels.index("vv")]) ** 2).astype(np.float32), window) + volume

    np.testing.assert_allclose(powers.sum(axis=0), span, rtol=1e-4)
    np.testing.assert_allclose(powers[2], volume, rtol=1e-4)


def test_copolar_powers_follow_the_co_polar_channels():
    """Checks the co-polar powers are the boxcar means of |HH|^2 and |VV|^2 and a wrong channel count is refused."""
    rng   = np.random.default_rng(8)
    stack = _channels(rng, 3, shape=(9, 7))

    copolar = PauliDecomposer((3, 3)).copolar_powers(stack)

    assert copolar.shape == (2, 9, 7) and copolar.dtype == np.float32
    np.testing.assert_allclose(copolar[0], uniform_filter((np.abs(stack[0]) ** 2).astype(np.float32), (3, 3)), rtol=1e-4)
    np.testing.assert_allclose(copolar[1], uniform_filter((np.abs(stack[2]) ** 2).astype(np.float32), (3, 3)), rtol=1e-4)

    with pytest.raises(ValueError):
        PauliDecomposer((1, 1)).copolar_powers(_channels(rng, 4))


def test_fractions_dominant_decibel_and_no_data():
    """Checks fractions sum to one, the dominant index follows the largest power, a zero pixel reads as no data and the decibel floor holds."""
    powers = np.zeros((3, 2, 3), dtype=np.float32)
    powers[0, 0, 0] = 3.0
    powers[1, 0, 1] = 2.0
    powers[2, 1, 0] = 1.0
    powers[:, 1, 1] = [1.0, 1.0, 2.0]
    powers[:, 1, 2] = [0.5, 0.25, 0.25]

    fractions = PauliDecomposer.fractions(powers)
    dominant  = PauliDecomposer.dominant(powers)
    decibel   = PauliDecomposer.decibel(powers)
    valid     = PauliDecomposer.valid(powers)

    assert valid.tolist() == [[True, True, False], [True, True, True]]
    np.testing.assert_allclose(fractions.sum(axis=0)[valid], 1.0, rtol=1e-6)
    np.testing.assert_allclose(fractions[:, 0, 2], 0.0)
    np.testing.assert_allclose(fractions[:, 1, 1], [0.25, 0.25, 0.5])
    assert dominant.tolist() == [[0, 1, -1], [2, 2, 0]]
    assert dominant.dtype == np.int8
    assert decibel.min() == pytest.approx(10.0 * np.log10(PauliDecomposer.DB_FLOOR))
    assert decibel[0, 0, 0] == pytest.approx(10.0 * np.log10(3.0))


def test_stretch_bounds_shared_and_per_channel():
    """Checks shared bounds pool every component and per-channel bounds follow each component."""
    powers_db = np.zeros((3, 10, 10), dtype=np.float32)
    powers_db[0] = np.linspace(-30.0, -20.0, 100).reshape(10, 10)
    powers_db[1] = np.linspace(-10.0, 0.0, 100).reshape(10, 10)
    powers_db[2] = np.linspace(-50.0, -40.0, 100).reshape(10, 10)
    valid        = np.ones((10, 10), dtype=bool)

    shared  = PauliDecomposer.stretch_bounds(powers_db, True, valid)
    channel = PauliDecomposer.stretch_bounds(powers_db, False, valid)

    assert shared["surface"] == shared["double"] == shared["volume"]
    assert shared["surface"][0] == pytest.approx(np.percentile(powers_db, 1.0))
    assert shared["surface"][1] == pytest.approx(np.percentile(powers_db, 99.0))
    assert channel["double"][0] > channel["surface"][1] > channel["volume"][1]


def test_stretch_bounds_ignore_no_data_margin():
    """Checks a zero-filled margin wider than the percentile tail leaves the bounds of the interior untouched, and an all-empty map is refused."""
    rng    = np.random.default_rng(9)
    stack  = _channels(rng, 3, shape=(20, 20))
    stack[:, :, 15:] = 0.0

    decomposer = PauliDecomposer((1, 1))
    powers     = decomposer.powers(stack)
    powers_db  = decomposer.decibel(powers)
    valid      = decomposer.valid(powers)
    interior   = decomposer.decibel(decomposer.powers(stack[:, :, :15]))

    assert valid[:, :15].all() and not valid[:, 15:].any()

    for shared in (True, False):
        masked   = PauliDecomposer.stretch_bounds(powers_db, shared, valid)
        expected = PauliDecomposer.stretch_bounds(interior, shared, np.ones((20, 15), dtype=bool))
        for key in PauliDecomposer.COMPONENTS:
            assert masked[key] == pytest.approx(expected[key], abs=1e-5)
            assert masked[key][0] > -100.0

    with pytest.raises(ValueError, match="valid pixel"):
        PauliDecomposer.stretch_bounds(powers_db, True, np.zeros((20, 20), dtype=bool))


def test_stretch_bounds_widen_degenerate_range():
    """Checks a constant component still receives a non-empty range."""
    powers_db = np.full((3, 4, 4), -12.0, dtype=np.float32)

    bounds = PauliDecomposer.stretch_bounds(powers_db, False, np.ones((4, 4), dtype=bool))

    assert bounds["volume"] == (-12.5, -11.5)


def test_composite_channel_mapping():
    """Checks double bounce paints red, volume green and surface blue."""
    powers_db = np.full((3, 1, 3), -40.0, dtype=np.float32)
    powers_db[1, 0, 0] = 0.0
    powers_db[2, 0, 1] = 0.0
    powers_db[0, 0, 2] = 0.0

    bounds = {key: (-40.0, 0.0) for key in PauliDecomposer.COMPONENTS}
    image  = PauliDecomposer.composite(powers_db, bounds)

    assert image.shape == (1, 3, 3)
    assert image.dtype == np.float32
    np.testing.assert_allclose(image[0, 0], [1.0, 0.0, 0.0])
    np.testing.assert_allclose(image[0, 1], [0.0, 1.0, 0.0])
    np.testing.assert_allclose(image[0, 2], [0.0, 0.0, 1.0])
