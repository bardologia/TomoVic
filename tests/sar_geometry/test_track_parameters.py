"""Tests parsing, collection, and serialisation of DLR step processing parameters.

Covers the idl2xml parameter parser, per-polarisation file resolution, the
acquisition geometry derived from the parameters, the right-looking validation,
and the shared/per-track payload split."""

from __future__ import annotations

import pytest

from tools.sar.track_parameters import (
    StepParameterFile,
    StepParameterResolver,
    TrackParameterCollector,
    TrackParameters,
)


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<idl2xml>
  <object name="step_processing_parameters">
    <parameter name="ident">
      <datatype length="1">string</datatype>
      <value>SARTOM0102</value>
    </parameter>
    <parameter name="antdir">
      <datatype length="1">long</datatype>
      <value>1</value>
    </parameter>
    <parameter name="lambda">
      <datatype length="1">double</datatype>
      <value>2.26195004272000011e-1</value>
    </parameter>
    <parameter name="da">
      <datatype length="1">double</datatype>
      <value>6.10865238197999982e-1</value>
    </parameter>
    <parameter name="h0">
      <datatype length="1">double</datatype>
      <value>3.71915192910869674e3</value>
    </parameter>
    <parameter name="terrain">
      <datatype length="1">double</datatype>
      <value>6.83882507324218736e2</value>
    </parameter>
    <parameter name="rref">
      <datatype length="1">double</datatype>
      <value>4.58523851573264007e3</value>
    </parameter>
    <parameter name="ang_range">
      <datatype length="2">double</datatype>
      <value>[1.50000000000000000e1,9.00000000000000000e1]</value>
    </parameter>
    <parameter name="r">
      <datatype length="1">pointer</datatype>
      <value>
        <parameter name="ptr">
          <datatype length="3">double</datatype>
          <value>[3.30000000000000000e3,4.00000000000000000e3,6.00000000000000000e3]</value>
        </parameter></value>
    </parameter>
    <parameter name="dims_info">
      <datatype length="1">struct</datatype>
      <value>
        <object name="step_dims_info">
          <parameter name="side_looking">
            <datatype length="1">string</datatype>
            <value>right</value>
          </parameter>
        </object></value>
    </parameter>
  </object>
</idl2xml>
"""


def _write_sample(directory, pols=("hh",)) -> None:
    """Writes the sample parameter XML under INF/INF-RDP for each polarisation.

    Args:
        directory: Track directory that receives the INF/INF-RDP subtree.
        pols: Polarisation codes to write one parameter file for.
    """
    product = directory / "INF" / "INF-RDP"
    product.mkdir(parents=True)

    for pol in pols:
        (product / f"pp_17sartom0102_L{pol}_t01L.xml").write_text(SAMPLE_XML, encoding="utf-8")


def test_parser_coerces_scalars_arrays_and_nested(tmp_path):
    """Verifies scalars, arrays, pointer arrays, and nested structs are typed correctly."""
    path = tmp_path / "pp.xml"
    path.write_text(SAMPLE_XML, encoding="utf-8")

    params = StepParameterFile(path).parse()

    assert params["ident"]                    == "SARTOM0102"
    assert params["antdir"]                   == 1
    assert params["lambda"]                   == pytest.approx(0.226195, rel=1e-5)
    assert params["ang_range"]                == [15.0, 90.0]
    assert params["r"]                        == [3300.0, 4000.0, 6000.0]
    assert params["dims_info"]["side_looking"] == "right"


def test_resolver_finds_pp_under_inf_rdp(tmp_path):
    """Verifies the parameter file is located under the track's INF/INF-RDP directory."""
    _write_sample(tmp_path / "PS02" / "T01L")

    resolved = StepParameterResolver().resolve_for_polarisation(tmp_path / "PS02" / "T01L", "hh")

    assert resolved.parent.parts[-2:] == ("INF", "INF-RDP")
    assert resolved.name              == "pp_17sartom0102_Lhh_t01L.xml"


def test_resolver_selects_requested_polarisation(tmp_path):
    """Verifies the requested polarisation is chosen among several parameter files."""
    _write_sample(tmp_path / "PS02" / "T01L", pols=("hh", "hv", "vv"))

    resolved = StepParameterResolver().resolve_for_polarisation(tmp_path / "PS02" / "T01L", "hv")

    assert resolved.name == "pp_17sartom0102_Lhv_t01L.xml"


def test_resolver_raises_when_polarisation_absent(tmp_path):
    """Verifies a missing polarisation raises FileNotFoundError."""
    _write_sample(tmp_path / "PS02" / "T01L", pols=("hh", "vv"))

    with pytest.raises(FileNotFoundError):
        StepParameterResolver().resolve_for_polarisation(tmp_path / "PS02" / "T01L", "hv")


def test_collector_builds_parameters_over_passes(tmp_path):
    """Verifies the collector labels, orders, and records one parameter file per pass."""
    for pass_name in ("PS02", "PS04"):
        _write_sample(tmp_path / "FL01" / pass_name / "T01L", pols=("hh", "hv"))

    directories = [tmp_path / "FL01" / "PS02" / "T01L", tmp_path / "FL01" / "PS04" / "T01L"]
    parameters  = TrackParameterCollector.from_pass_directories(directories, "hv").collect()

    assert parameters.labels      == ["FL01_PS02", "FL01_PS04"]
    assert parameters.reference   == "FL01_PS02"
    assert parameters.n_tracks    == 2
    assert all(path.endswith("INF/INF-RDP/pp_17sartom0102_Lhv_t01L.xml") for path in parameters.track_files)


def test_collector_rejects_duplicate_labels(tmp_path):
    """Verifies two directories resolving to the same label are rejected."""
    _write_sample(tmp_path / "FL01" / "PS02" / "T01L", pols=("hv",))

    directories = [tmp_path / "FL01" / "PS02" / "T01L", tmp_path / "FL01" / "PS02" / "T01L"]

    with pytest.raises(ValueError, match="duplicate labels"):
        TrackParameterCollector.from_pass_directories(directories, "hv")


def test_derived_geometry_matches_acquisition(tmp_path):
    """Verifies the derived look side, depression angle in degrees, and slant range extent in metres."""
    path = tmp_path / "pp.xml"
    path.write_text(SAMPLE_XML, encoding="utf-8")

    parameters = TrackParameters(labels=["FL01_PS02"], parameters=[StepParameterFile(path).parse()])
    geometry   = parameters.derived()[0]

    assert geometry["look_side"]            == "right"
    assert geometry["depression_angle_deg"] == pytest.approx(35.0, abs=1e-6)
    assert geometry["slant_range_near_m"]   == 3300.0
    assert geometry["slant_range_far_m"]    == 6000.0
    assert geometry["look_angle_far_deg"]   > geometry["look_angle_near_deg"]


def test_derived_rejects_height_above_the_near_slant_range(tmp_path):
    """Verifies a flight height above the near slant range is rejected."""
    path = tmp_path / "pp.xml"
    path.write_text(SAMPLE_XML, encoding="utf-8")

    params  = StepParameterFile(path).parse()
    corrupt = {**params, "h0": params["r"][0] + params["terrain"] + 1.0}

    with pytest.raises(ValueError, match="must be positive and below the nearest slant range"):
        TrackParameters(labels=["FL01_PS02"], parameters=[corrupt]).derived()


def test_validate_right_looking_accepts_right_and_rejects_left(tmp_path):
    """Verifies antdir is checked and a left-looking track is named in the error."""
    path = tmp_path / "pp.xml"
    path.write_text(SAMPLE_XML, encoding="utf-8")

    params = StepParameterFile(path).parse()
    TrackParameters(labels=["FL01_PS02"], parameters=[params]).validate_right_looking()

    flipped = {**params, "antdir": -1}
    with pytest.raises(ValueError, match=r"\['FL01_PS02'\].*left-looking"):
        TrackParameters(labels=["FL01_PS02"], parameters=[flipped]).validate_right_looking()


def test_collector_rejects_left_looking_track(tmp_path):
    """Verifies collection aborts on a left-looking parameter file."""
    path = tmp_path / "pp.xml"
    path.write_text(SAMPLE_XML.replace("<value>1</value>", "<value>-1</value>", 1), encoding="utf-8")

    assert StepParameterFile(path).parse()["antdir"] == -1

    with pytest.raises(ValueError, match="left-looking"):
        TrackParameterCollector({"FL01_PS02": path}).collect()


def test_payload_roundtrip_preserves_parameters(tmp_path):
    """Verifies saving and loading preserves arrays and nested parameter structs."""
    path = tmp_path / "pp.xml"
    path.write_text(SAMPLE_XML, encoding="utf-8")

    parameters = TrackParameters(labels=["FL01_PS02"], parameters=[StepParameterFile(path).parse()])
    saved      = parameters.save(tmp_path / TrackParameters.FILENAME)
    restored   = TrackParameters.load(saved)

    assert restored.labels                       == parameters.labels
    assert restored.parameters[0]["r"]           == [3300.0, 4000.0, 6000.0]
    assert restored.parameters[0]["dims_info"]   == {"side_looking": "right"}


def test_payload_deduplicates_shared_fields():
    """Verifies identical fields move to the shared block and the round trip restores them."""
    primary   = {"da": 0.61, "r": [1.0, 2.0, 3.0], "h0": 3719.1, "ident": "A"}
    secondary = {"da": 0.61, "r": [1.0, 2.0, 3.0], "h0": 3719.0, "ident": "B"}

    parameters = TrackParameters(labels=["FL01_PS02", "FL01_PS04"], parameters=[primary, secondary])
    payload    = parameters.to_payload()

    assert payload["shared"]                 == {"da": 0.61, "r": [1.0, 2.0, 3.0]}
    assert payload["per_track"]["FL01_PS02"] == {"h0": 3719.1, "ident": "A"}
    assert payload["per_track"]["FL01_PS04"] == {"h0": 3719.0, "ident": "B"}
    assert "r" not in payload["per_track"]["FL01_PS02"]

    restored = TrackParameters.from_payload(payload)

    assert restored.parameters[0] == primary
    assert restored.parameters[1] == secondary


def test_payload_rejects_extra_keys_on_secondary_track():
    """Verifies a secondary track carrying an extra parameter key is rejected."""
    primary   = {"da": 0.61, "h0": 3719.1}
    secondary = {"da": 0.61, "h0": 3719.0, "cal_dt": 1.5}

    parameters = TrackParameters(labels=["FL01_PS02", "FL01_PS04"], parameters=[primary, secondary])

    with pytest.raises(ValueError, match="extra.*cal_dt"):
        parameters.to_payload()


def test_payload_rejects_missing_keys_on_secondary_track():
    """Verifies a secondary track missing a parameter key is rejected."""
    primary   = {"da": 0.61, "h0": 3719.1}
    secondary = {"da": 0.61}

    parameters = TrackParameters(labels=["FL01_PS02", "FL01_PS04"], parameters=[primary, secondary])

    with pytest.raises(ValueError, match="missing.*h0"):
        parameters.to_payload()
