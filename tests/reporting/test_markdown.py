"""Tests covering the markdown report primitives: scalar formatting, tables and documents."""

from __future__ import annotations


import pytest

from tools.reporting.markdown import MarkdownDoc, MarkdownTable, ScalarFormatter


def test_scalar_formatter_none_returns_empty():
    """Verifies None renders as the default empty placeholder."""
    assert ScalarFormatter.format_scalar(None) == ScalarFormatter.EMPTY


def test_scalar_formatter_custom_empty():
    """Verifies a caller-supplied placeholder replaces the default for None."""
    assert ScalarFormatter.format_scalar(None, empty="N/A") == "N/A"


def test_scalar_formatter_float_default_precision():
    """Verifies floats are rounded to the requested significant precision."""
    assert ScalarFormatter.format_scalar(3.14159265, precision=5) == "3.1416"


def test_scalar_formatter_float_precision_three():
    """Verifies a precision of three digits is honoured for repeating decimals."""
    assert ScalarFormatter.format_scalar(2.0 / 3.0, precision=3) == "0.667"


def test_scalar_formatter_adaptive_large():
    """Verifies adaptive formatting switches large magnitudes to scientific notation."""
    assert ScalarFormatter.format_scalar(12345.678, adaptive=True) == "1.2346e+04"


def test_scalar_formatter_adaptive_small():
    """Verifies adaptive formatting switches small magnitudes to scientific notation."""
    assert ScalarFormatter.format_scalar(1e-5, adaptive=True) == "1.0000e-05"


def test_scalar_formatter_adaptive_zero_stays_g():
    """Verifies adaptive formatting leaves zero in general notation."""
    assert ScalarFormatter.format_scalar(0.0, adaptive=True) == "0"


def test_scalar_formatter_adaptive_midrange_uses_g():
    """Verifies mid-range magnitudes stay in general notation under adaptive formatting."""
    assert ScalarFormatter.format_scalar(12.5, adaptive=True) == "12.5"


def test_scalar_formatter_list_joined():
    """Verifies lists render as comma-separated values."""
    assert ScalarFormatter.format_scalar([1, 2, 3]) == "1, 2, 3"


def test_scalar_formatter_tuple_joined():
    """Verifies tuples render as comma-separated values."""
    assert ScalarFormatter.format_scalar((4, 5)) == "4, 5"


def test_scalar_formatter_int_passthrough():
    """Verifies integers render without decimal padding."""
    assert ScalarFormatter.format_scalar(42) == "42"


def test_scalar_formatter_str_passthrough():
    """Verifies strings pass through unchanged."""
    assert ScalarFormatter.format_scalar("abc") == "abc"


def test_table_columns_stringified():
    """Verifies column headers are coerced to strings."""
    table = MarkdownTable([1, "b", 3.0])
    assert table.columns == ["1", "b", "3.0"]


def test_table_default_alignment_all_left():
    """Verifies columns default to left alignment."""
    table = MarkdownTable(["a", "b"])
    assert table.align == ["left", "left"]


def test_table_is_empty_initially():
    """Verifies a freshly built table reports itself as empty."""
    assert MarkdownTable(["x"]).is_empty()


def test_table_not_empty_after_add():
    """Verifies adding a row clears the empty state."""
    table = MarkdownTable(["x"]).add_row("v")
    assert not table.is_empty()


def test_table_add_row_returns_self():
    """Verifies add_row returns the table for chaining."""
    table = MarkdownTable(["x"])
    assert table.add_row("v") is table


def test_table_add_row_pads_missing_cells_with_empty():
    """Verifies short rows are padded with the empty placeholder."""
    table = MarkdownTable(["a", "b", "c"])
    table.add_row("only")
    assert table.rows[0] == ["only", MarkdownTable.EMPTY, MarkdownTable.EMPTY]


def test_table_add_row_none_cell_becomes_empty():
    """Verifies a None cell renders as the empty placeholder."""
    table = MarkdownTable(["a", "b"])
    table.add_row("x", None)
    assert table.rows[0] == ["x", MarkdownTable.EMPTY]


def test_table_add_rows_bulk():
    """Verifies add_rows appends every supplied row."""
    table = MarkdownTable(["a", "b"])
    table.add_rows([("1", "2"), ("3", "4")])
    assert len(table.rows) == 2


def test_table_render_structure():
    """Verifies rendering emits a header, a separator of dashes and one body line."""
    table = MarkdownTable(["Key", "Value"])
    table.add_row("alpha", "1")
    lines = table.render()

    assert len(lines) == 3
    assert lines[0].startswith("|") and lines[0].endswith("|")
    assert set(lines[1].replace("|", "").replace(":", "").replace(" ", "")) == {"-"}
    assert "alpha" in lines[2] and "1" in lines[2]


def test_table_render_pipe_count_consistent():
    """Verifies every rendered line carries the same number of column separators."""
    table = MarkdownTable(["a", "b", "c"])
    table.add_row("x", "y", "z")
    lines       = table.render()
    pipe_counts = {line.count("|") for line in lines}
    assert pipe_counts == {4}


def test_table_render_column_widths_align():
    """Verifies all rendered lines share one width, so columns line up."""
    table = MarkdownTable(["aa", "b"])
    table.add_row("longcell", "y")
    lines   = table.render()
    lengths = {len(line) for line in lines}
    assert len(lengths) == 1


def test_table_separator_right_alignment():
    """Verifies right-aligned columns mark the separator only on the right."""
    table = MarkdownTable(["num"], align=["right"])
    table.add_row("1")
    inner = table.render()[1].strip()[1:-1].strip()
    assert inner.endswith(":")
    assert not inner.startswith(":")


def test_table_separator_center_alignment():
    """Verifies centred columns mark the separator on both sides."""
    table = MarkdownTable(["num"], align=["center"])
    table.add_row("1")
    sep   = table.render()[1].strip()
    inner = sep[1:-1].strip()
    assert inner.startswith(":") and inner.endswith(":")


def test_table_separator_left_plain_dashes():
    """Verifies left-aligned columns leave the separator free of alignment colons."""
    table = MarkdownTable(["num"], align=["left"])
    table.add_row("1")
    sep = table.render()[1]
    assert ":" not in sep


def test_table_right_aligned_cell_padding():
    """Verifies right-aligned body cells are padded on the left."""
    table = MarkdownTable(["value"], align=["right"])
    table.add_row("x")
    body = table.render()[2]
    cell = body.split("|")[1]
    assert cell.startswith(" ") and cell.endswith("x ")


def test_table_min_width_three():
    """Verifies rendered columns are at least three characters wide."""
    table = MarkdownTable(["a"])
    table.add_row("b")
    width = len(table.render()[0].split("|")[1].strip().ljust(3))
    assert width >= 3


def test_doc_empty_render_newline():
    """Verifies an empty document renders as a single newline."""
    assert MarkdownDoc().render() == "\n"


def test_doc_title_creates_h1():
    """Verifies a constructor title becomes the level-one heading."""
    doc = MarkdownDoc("Report")
    assert doc.render().startswith("# Report")


def test_doc_heading_levels():
    """Verifies the heading level controls the number of hashes."""
    doc = MarkdownDoc()
    doc.heading("Sub", level=2)
    assert "## Sub" in doc.render()


def test_doc_heading_inserts_blank_before_when_nonempty():
    """Verifies a heading added to a non-empty document is preceded by a blank line."""
    doc = MarkdownDoc("Top")
    doc.heading("Second", level=2)
    text = doc.render()
    assert "# Top" in text
    assert "## Second" in text
    assert text.index("# Top") < text.index("## Second")
    assert "\n\n## Second" in text


def test_doc_paragraph():
    """Verifies paragraph text reaches the rendered document."""
    doc = MarkdownDoc()
    doc.paragraph("hello world")
    assert "hello world" in doc.render()


def test_doc_bold_kv():
    """Verifies bold_kv renders a bold key with the value in inline code."""
    doc = MarkdownDoc()
    doc.bold_kv("loss", 0.5)
    assert "**loss:** `0.5`" in doc.render()


def test_doc_raw_no_trailing_blank():
    """Verifies raw appends the line verbatim without a trailing blank."""
    doc = MarkdownDoc()
    doc.raw("rawline")
    assert doc.lines == ["rawline"]


def test_doc_blank_adds_empty_line():
    """Verifies blank appends one empty line."""
    doc = MarkdownDoc()
    doc.blank()
    assert doc.lines == [""]


def test_doc_image_markdown():
    """Verifies image renders markdown image syntax with the given alt text and path."""
    doc = MarkdownDoc()
    doc.image("alt text", "fig.png")
    assert "![alt text](fig.png)" in doc.render()


def test_doc_methods_chainable():
    """Verifies the builder methods return the document for chaining."""
    doc    = MarkdownDoc()
    result = doc.heading("h").paragraph("p").bold_kv("k", "v").blank()
    assert result is doc


def test_doc_kv_table_from_mapping():
    """Verifies a key-value table built from a mapping renders its keys as inline code."""
    doc = MarkdownDoc()
    doc.kv_table({"a": 1, "b": 2})
    text = doc.render()
    assert "`a`" in text and "`b`" in text


def test_doc_kv_table_from_iterable():
    """Verifies a key-value table accepts an iterable of pairs."""
    doc = MarkdownDoc()
    doc.kv_table([("x", 10), ("y", 20)])
    text = doc.render()
    assert "`x`" in text and "10" in text


def test_doc_kv_table_no_code_keys():
    """Verifies code_keys=False renders keys as plain text."""
    doc = MarkdownDoc()
    doc.kv_table({"plain": 1}, code_keys=False)
    text = doc.render()
    assert "`plain`" not in text
    assert "plain" in text


def test_doc_kv_table_custom_header():
    """Verifies a custom header pair replaces the default column titles."""
    doc = MarkdownDoc()
    doc.kv_table({"a": 1}, header=("Metric", "Score"))
    text = doc.render()
    assert "Metric" in text and "Score" in text


def test_doc_table_appends_render_plus_blank():
    """Verifies embedding a table appends its lines followed by a blank line."""
    table = MarkdownTable(["a"]).add_row("1")
    doc   = MarkdownDoc()
    doc.table(table)
    assert doc.lines[-1] == ""
    assert any("a" in line for line in doc.lines)


def test_doc_render_ends_with_single_newline():
    """Verifies the rendered document ends with exactly one newline."""
    doc      = MarkdownDoc("T")
    rendered = doc.render()
    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")


def test_doc_save_writes_file(tmp_path):
    """Verifies save creates missing parent directories and writes the rendered text."""
    doc = MarkdownDoc("Saved")
    doc.paragraph("body")
    out = doc.save(tmp_path / "nested" / "report.md")

    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("# Saved")


def test_doc_save_returns_path(tmp_path):
    """Verifies save returns the path it wrote to."""
    doc = MarkdownDoc("X")
    out = doc.save(tmp_path / "x.md")
    assert out == tmp_path / "x.md"


def test_doc_save_roundtrip_equals_render(tmp_path):
    """Verifies the saved file content equals the rendered document."""
    doc = MarkdownDoc("Round")
    doc.kv_table({"k": "v"})
    out = doc.save(tmp_path / "r.md")
    assert out.read_text(encoding="utf-8") == doc.render()
@pytest.mark.real_data
def test_table_render_real_baselines(baselines_json):
    """Verifies a two-column table of real baseline entries renders with consistent separators."""
    table = MarkdownTable(["Key", "Value"])
    for k, v in list(baselines_json.items())[:6]:
        table.add_row(str(k), ScalarFormatter.format_scalar(v) if not isinstance(v, (dict, list)) else "...")
    lines = table.render()
    assert all(line.count("|") == 3 for line in lines)
