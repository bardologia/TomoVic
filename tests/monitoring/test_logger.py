"""Tests covering the Rich-backed experiment Logger: level parsing, file output, banners, tables, timers, and the null variant."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pytest

from tools.monitoring.logger       import Logger, NullLogger, LiveMonitor, get_console
from tools.runtime.config_cli      import ConfigCli
from tools.runtime.machine_profile import MachineProfile


@dataclass
class EntryConfig:
    """Two-leaf config standing in for an entry configuration."""
    seed    : int = 42
    workers : int = 8


def _read_log(log_dir, name="experiment"):
    """Returns the text of the log file written under the given directory."""
    return (log_dir / f"{name}.log").read_text(encoding="utf-8")


def test_get_console_is_singleton():
    """Verifies repeated get_console calls hand back the same console object."""
    a = get_console()
    b = get_console()

    assert a is b


def test_init_creates_log_dir_and_file(tmp_path):
    """Verifies construction creates the log directory and the named log file."""
    log_dir = tmp_path / "logs"
    logger  = Logger(log_dir=str(log_dir), name="exp_init")

    assert log_dir.is_dir()
    assert (log_dir / "exp_init.log").is_file()

    logger.close()


def test_init_without_log_dir_has_no_file_handler():
    """Verifies an empty log directory leaves the logger without a file handler."""
    logger = Logger(log_dir="", name="exp_nofile")

    assert logger._file_handler is None

    logger.close()


def test_init_raises_when_the_log_dir_lies_under_a_file(tmp_path):
    """Verifies an unusable log directory raises at construction instead of running without a log file."""
    blocker = tmp_path / "afile"
    blocker.write_text("x")

    with pytest.raises(NotADirectoryError):
        Logger(log_dir=str(blocker / "logs"), name="exp_blocked")


def test_level_parsing_known(tmp_path):
    """Verifies an uppercase level name sets the underlying logging level."""
    logger = Logger(log_dir=str(tmp_path), name="exp_lvl", level="DEBUG")

    assert logger.logger.level == logging.DEBUG

    logger.close()


def test_level_parsing_case_insensitive(tmp_path):
    """Verifies a lowercase level name maps to the same logging level."""
    logger = Logger(log_dir=str(tmp_path), name="exp_lvl2", level="warning")

    assert logger.logger.level == logging.WARNING

    logger.close()


def test_level_parsing_unknown_raises(tmp_path):
    """Verifies an unrecognised level name is refused instead of silently becoming INFO."""
    with pytest.raises(ValueError, match="Unknown log level 'BOGUS'"):
        Logger(log_dir=str(tmp_path), name="exp_lvl3", level="BOGUS")


def test_info_written_to_file(tmp_path):
    """Verifies info messages reach the log file carrying the INFO tag."""
    logger = Logger(log_dir=str(tmp_path), name="exp_info")
    logger.info("hello world")
    logger.close()

    contents = _read_log(tmp_path, "exp_info")

    assert "hello world" in contents
    assert "INFO" in contents


def test_warning_and_error_written_to_file(tmp_path):
    """Verifies warning and error messages reach the log file with their level tags."""
    logger = Logger(log_dir=str(tmp_path), name="exp_we")
    logger.warning("be careful")
    logger.error("it broke")
    logger.close()

    contents = _read_log(tmp_path, "exp_we")

    assert "be careful" in contents
    assert "it broke" in contents
    assert "WARNING" in contents
    assert "ERROR" in contents


def test_debug_suppressed_below_level(tmp_path):
    """Verifies debug messages are dropped while the level is INFO."""
    logger = Logger(log_dir=str(tmp_path), name="exp_dbg", level="INFO")
    logger.debug("invisible debug")
    logger.close()

    contents = _read_log(tmp_path, "exp_dbg")

    assert "invisible debug" not in contents


def test_debug_emitted_when_level_debug(tmp_path):
    """Verifies debug messages are written once the level is DEBUG."""
    logger = Logger(log_dir=str(tmp_path), name="exp_dbg2", level="DEBUG")
    logger.debug("visible debug")
    logger.close()

    contents = _read_log(tmp_path, "exp_dbg2")

    assert "visible debug" in contents


def test_section_writes_uppercase_marker(tmp_path):
    """Verifies section titles are uppercased behind a '>>>' marker."""
    logger = Logger(log_dir=str(tmp_path), name="exp_sec")
    logger.section("data loading")
    logger.close()

    contents = _read_log(tmp_path, "exp_sec")

    assert ">>> DATA LOADING" in contents


def test_section_writes_banner_rules(tmp_path):
    """Verifies a section line is fenced above and below by full-width rules."""
    logger = Logger(log_dir=str(tmp_path), name="exp_sec_bar")
    logger.section("data loading")
    logger.close()

    contents = _read_log(tmp_path, "exp_sec_bar")
    bar      = "=" * Logger.FILE_RULE_WIDTH
    lines    = contents.splitlines()
    index    = next(i for i, line in enumerate(lines) if ">>> DATA LOADING" in line)

    assert lines[index - 1] == bar
    assert lines[index + 1] == bar
    assert "[INFO]" in lines[index]


def test_second_section_includes_elapsed(tmp_path):
    """Verifies only sections after the first carry an elapsed-time suffix."""
    logger = Logger(log_dir=str(tmp_path), name="exp_sec_dt")
    logger.section("first")
    logger.section("second")
    logger.close()

    contents = _read_log(tmp_path, "exp_sec_dt")

    assert ">>> FIRST\n" in contents
    assert ">>> SECOND  (+" in contents


def test_header_banner_written(tmp_path):
    """Verifies the run header and end banners bracket the log body."""
    logger = Logger(log_dir=str(tmp_path), name="exp_head")
    logger.close()

    contents = _read_log(tmp_path, "exp_head")

    assert ">>> RUN exp_head" in contents
    assert ">>> END exp_head" in contents


def test_header_names_host_pid_and_command(tmp_path, monkeypatch):
    """Verifies the file banner records the host and pid and the header records the command line."""
    import os
    import socket
    import sys

    monkeypatch.setattr(sys, "argv", ["train_backbone.py", "--seeds", "[0,1,2]"])
    logger = Logger(log_dir=str(tmp_path), name="exp_host")
    logger.close()

    contents = _read_log(tmp_path, "exp_host")

    assert f"host {socket.gethostname()}" in contents
    assert f"pid {os.getpid()}" in contents
    assert "Command : train_backbone.py --seeds '[0,1,2]'" in contents


def test_header_names_the_detached_output(tmp_path, monkeypatch):
    """Verifies a detached child names its redirected stdout file in the log header."""
    from tools.runtime.detacher import Detacher

    monkeypatch.setattr(Detacher, "output_path", "/runs/logs/train_backbone_20261002.out")
    logger = Logger(log_dir=str(tmp_path), name="exp_detached")
    logger.close()

    assert "Detached output : /runs/logs/train_backbone_20261002.out" in _read_log(tmp_path, "exp_detached")


def test_header_reports_the_configuration_sources_of_the_parsed_command_line(tmp_path, monkeypatch):
    """Verifies a Logger opened after ConfigCli parsed the process arguments records the profile state and every override."""
    cli = ConfigCli(EntryConfig(), profile=MachineProfile(None))
    cli.apply(["--seed", "7"])
    monkeypatch.setattr(ConfigCli, "parsed", cli)

    logger = Logger(log_dir=str(tmp_path), name="exp_sources")
    logger.close()

    text = _read_log(tmp_path, "exp_sources")

    assert "Configuration sources" in text
    assert f"disabled by an empty {MachineProfile.ENV_VAR}" in text
    assert "seed" in text and "command line" in text
    assert "42" in text and "7" in text


def test_header_without_a_parsed_command_line_names_no_sources(tmp_path, monkeypatch):
    """Verifies a process whose configuration no ConfigCli parsed gets the plain header."""
    monkeypatch.setattr(ConfigCli, "parsed", None)

    logger = Logger(log_dir=str(tmp_path), name="exp_plain")
    logger.close()

    assert "Configuration sources" not in _read_log(tmp_path, "exp_plain")


def test_default_file_mode_appends_to_an_earlier_run(tmp_path):
    """Verifies a second run of the same name keeps the first run's record above its own banner."""
    first = Logger(log_dir=str(tmp_path), name="exp_append")
    first.info("first attempt")
    first.close()

    second = Logger(log_dir=str(tmp_path), name="exp_append")
    second.info("second attempt")
    second.close()

    contents = _read_log(tmp_path, "exp_append")

    assert contents.count(">>> RUN exp_append") == 2
    assert contents.index("first attempt") < contents.index("second attempt")


def test_truncate_mode_replaces_an_earlier_run(tmp_path):
    """Verifies file_mode 'w' still truncates when a caller asks for it."""
    first = Logger(log_dir=str(tmp_path), name="exp_trunc")
    first.info("first attempt")
    first.close()

    second = Logger(log_dir=str(tmp_path), name="exp_trunc", file_mode="w")
    second.close()

    assert "first attempt" not in _read_log(tmp_path, "exp_trunc")


def test_fmt_duration_scales():
    """Verifies duration formatting switches between seconds, minutes, and hours."""
    assert Logger._fmt_duration(12.34)   == "12.3s"
    assert Logger._fmt_duration(75.0)    == "1m15s"
    assert Logger._fmt_duration(3725.0)  == "1h02m05s"


def test_subsection_writes_marker(tmp_path):
    """Verifies subsections are logged at INFO behind a '>' marker."""
    logger = Logger(log_dir=str(tmp_path), name="exp_sub")
    logger.subsection("step one")
    logger.close()

    contents = _read_log(tmp_path, "exp_sub")
    line     = next(line for line in contents.splitlines() if "> step one" in line)

    assert "[INFO]" in line


def test_ok_writes_plus_marker(tmp_path):
    """Verifies success messages are written behind a '+' marker."""
    logger = Logger(log_dir=str(tmp_path), name="exp_ok")
    logger.ok("done")
    logger.close()

    contents = _read_log(tmp_path, "exp_ok")

    assert "+ done" in contents


def test_fmt_float_uses_six_sig():
    """Verifies floats are rendered with six significant digits."""
    assert Logger._fmt(3.14159265) == "3.14159"
    assert Logger._fmt(1000000.0)  == "1e+06"


def test_fmt_non_float_is_str():
    """Verifies non-float values are rendered with str."""
    assert Logger._fmt(42)    == "42"
    assert Logger._fmt("abc") == "abc"
    assert Logger._fmt(None)  == "None"


def test_kv_table_does_not_crash(tmp_path):
    """Verifies a key-value table renders with mixed float, string, and None values."""
    logger = Logger(log_dir=str(tmp_path), name="exp_kv")
    logger.kv_table({"alpha": 1.5, "beta": "x", "gamma": None}, title="Params")
    logger.close()


def test_kv_table_empty_does_not_crash(tmp_path):
    """Verifies an empty key-value table renders without error."""
    logger = Logger(log_dir=str(tmp_path), name="exp_kv2")
    logger.kv_table({})
    logger.close()


def test_metrics_table_does_not_crash(tmp_path):
    """Verifies a metrics table renders when a requested column is missing from the rows."""
    logger = Logger(log_dir=str(tmp_path), name="exp_mt")
    rows   = [{"epoch": 1, "loss": 0.5}, {"epoch": 2, "loss": 0.25}]
    logger.metrics_table(rows, columns=["epoch", "loss", "missing"], title="Train")
    logger.close()


def test_panel_and_rule_and_render_do_not_crash(tmp_path):
    """Verifies panel, rule, and render emit without error."""
    logger = Logger(log_dir=str(tmp_path), name="exp_panel")
    logger.panel("body text", title="Title")
    logger.rule("a rule")
    logger.render("rendered text")
    logger.close()


def test_timer_logs_completion(tmp_path):
    """Verifies the timer context manager logs a completion line."""
    logger = Logger(log_dir=str(tmp_path), name="exp_timer")
    with logger.timer("phase"):
        pass
    logger.close()

    contents = _read_log(tmp_path, "exp_timer")

    assert "phase completed in" in contents


def test_timer_logs_failure_and_reraises(tmp_path):
    """Verifies the timer logs a failure line and lets the exception propagate."""
    logger = Logger(log_dir=str(tmp_path), name="exp_timer_fail")
    with pytest.raises(ValueError):
        with logger.timer("phase"):
            raise ValueError("boom")
    logger.close()

    contents = _read_log(tmp_path, "exp_timer_fail")

    assert "phase failed after" in contents
    assert "ValueError: boom" in contents
    assert "phase completed in" not in contents


def test_track_yields_progress(tmp_path):
    """Verifies the track context manager yields a usable progress object."""
    logger = Logger(log_dir=str(tmp_path), name="exp_track")
    with logger.track(transient=True) as progress:
        task = progress.add_task("work", total=3)
        progress.advance(task, 3)
    logger.close()


def test_progress_bar_aliases_track():
    """Verifies progress_bar is the same callable as track."""
    assert Logger.progress_bar is Logger.track


def test_live_monitor_updates(tmp_path):
    """Verifies live-monitor updates accumulate metrics across successive calls."""
    logger = Logger(log_dir=str(tmp_path), name="exp_live")
    with logger.live_monitor(title="Run") as monitor:
        monitor.update(loss=0.1, step=5)
        monitor.update(loss=0.05)

    assert monitor._metrics["loss"] == 0.05
    assert monitor._metrics["step"] == 5

    logger.close()


def test_context_manager_closes(tmp_path):
    """Verifies context-manager use writes the body and a closing duration line."""
    with Logger(log_dir=str(tmp_path), name="exp_ctx") as logger:
        logger.info("inside")

    contents = _read_log(tmp_path, "exp_ctx")

    assert "inside" in contents
    assert "[End] Duration:" in contents


def test_context_manager_logs_exception(tmp_path):
    """Verifies an exception escaping the context manager is recorded with its traceback under an ABORTED banner."""
    with pytest.raises(RuntimeError):
        with Logger(log_dir=str(tmp_path), name="exp_ctx_exc") as logger:
            raise RuntimeError("model diverged")

    contents = _read_log(tmp_path, "exp_ctx_exc")

    assert "[ERROR] [Aborted] RuntimeError: model diverged" in contents
    assert "Traceback (most recent call last)" in contents
    assert "[ERROR] >>> ABORTED exp_ctx_exc" in contents
    assert "[Aborted] Duration:" in contents
    assert ">>> END exp_ctx_exc" not in contents
    assert contents.index("Traceback") < contents.index(">>> ABORTED")


def test_close_with_error_records_the_abort(tmp_path):
    """Verifies close(error) from a caller's except branch writes the same abort record as the context manager."""
    logger = Logger(log_dir=str(tmp_path), name="exp_close_err")
    try:
        raise FloatingPointError("train loss is non-finite at step 12")
    except FloatingPointError as exc:
        logger.close(exc)

    contents = _read_log(tmp_path, "exp_close_err")

    assert "[Aborted] FloatingPointError: train loss is non-finite at step 12" in contents
    assert ">>> ABORTED exp_close_err" in contents
    assert ">>> END exp_close_err" not in contents


def test_clean_system_exit_closes_as_completed(tmp_path):
    """Verifies SystemExit with code 0 ends the log with END, while a non-zero code counts as an abort."""
    with pytest.raises(SystemExit):
        with Logger(log_dir=str(tmp_path), name="exp_exit0"):
            raise SystemExit(0)
    with pytest.raises(SystemExit):
        with Logger(log_dir=str(tmp_path), name="exp_exit2"):
            raise SystemExit(2)

    assert ">>> END exp_exit0" in _read_log(tmp_path, "exp_exit0")
    assert ">>> ABORTED exp_exit2" in _read_log(tmp_path, "exp_exit2")


def test_close_removes_all_handlers(tmp_path):
    """Verifies close detaches every handler and clears the file handler."""
    logger = Logger(log_dir=str(tmp_path), name="exp_close")
    logger.close()

    assert logger.logger.handlers == []
    assert logger._file_handler is None


def test_reinit_same_name_resets_handlers(tmp_path):
    """Verifies re-creating a logger under the same name leaves exactly two handlers."""
    a = Logger(log_dir=str(tmp_path), name="dup")
    b = Logger(log_dir=str(tmp_path), name="dup")

    assert len(b.logger.handlers) == 2

    b.close()


def test_propagate_disabled(tmp_path):
    """Verifies the underlying logger does not propagate to ancestor loggers."""
    logger = Logger(log_dir=str(tmp_path), name="exp_prop")

    assert logger.logger.propagate is False

    logger.close()


def test_live_monitor_render_returns_panel():
    """Verifies the live monitor renders a panel from its accumulated metrics."""
    monitor = LiveMonitor(get_console(), title="T")
    monitor.update(a=1.234567, b="text", big=5000.0)

    panel = monitor._render()

    assert panel is not None


def test_null_logger_swallows_everything():
    """Verifies NullLogger returns None for both known and arbitrary method names."""
    nl = NullLogger()

    assert nl.info("x")            is None
    assert nl.section("y")         is None
    assert nl.anything("a", b=2)   is None
    assert nl.kv_table({"k": "v"}) is None


from tools.monitoring import logger as logger_module


def test_progress_bars_refresh_at_rich_default_rate_so_console_tiles_stay_live():
    """A unit's stdout is a file the console tile tails; the bar redraws at Rich's default 8 Hz so the tile animates instead of freezing between redraws."""
    console  = logger_module.Console(force_terminal=True, file=open("/dev/null", "w"))
    progress = logger_module._make_progress(console)

    assert logger_module.PROGRESS_REFRESH_HZ == 8.0
    assert progress.live.refresh_per_second == logger_module.PROGRESS_REFRESH_HZ


def test_progress_bars_stop_without_waiting_for_the_next_redraw():
    """Leaving the progress context returns at once instead of waiting out the refresh interval."""
    console  = logger_module.Console(force_terminal=True, file=open("/dev/null", "w"))
    progress = logger_module._make_progress(console)
    started  = time.monotonic()

    with progress:
        progress.add_task("epoch", total=10)

    assert time.monotonic() - started < 2.0


def test_live_monitor_shares_the_progress_refresh_rate():
    """The metric panel redraws at the same rate as the progress bars."""
    console = logger_module.Console(theme=logger_module._THEME, force_terminal=True, file=open("/dev/null", "w"))

    with logger_module.LiveMonitor(console) as monitor:
        assert monitor._live.refresh_per_second == logger_module.PROGRESS_REFRESH_HZ


def test_adopt_writes_another_loggers_records_into_the_file_until_close(tmp_path):
    """Verifies an adopted logger's warnings, traceback included, land in the log file, and stop landing there once the run closes."""
    lg      = Logger(log_dir=str(tmp_path), name="adopt_run")
    foreign = logging.getLogger("adopt_foreign_library")
    foreign.setLevel(logging.WARNING)

    lg.adopt("adopt_foreign_library")
    try:
        raise ValueError("objective returned nan")
    except ValueError:
        foreign.warning("Trial 3 failed", exc_info=True)

    lg.close()
    foreign.warning("after close")

    text = (tmp_path / "adopt_run.log").read_text()
    assert "[WARNING] Trial 3 failed" in text
    assert "ValueError: objective returned nan" in text
    assert "after close" not in text
    assert lg.logger.handlers == []
    assert foreign.handlers   == []



def test_close_with_an_error_whose_text_looks_like_markup(tmp_path):
    """An exception message holding a closing tag such as [/tmp/x] still reaches the file with its ABORTED banner instead of raising a MarkupError."""
    logger = Logger(log_dir=str(tmp_path), name="markup_abort", level="INFO")

    logger.close(RuntimeError("cannot open [/tmp/x] [bold]"))

    contents = (tmp_path / "markup_abort.log").read_text(encoding="utf-8")

    assert "[Aborted] RuntimeError: cannot open [/tmp/x] [bold]" in contents
    assert ">>> ABORTED markup_abort" in contents
