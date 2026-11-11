"""Reference screenshots of the original TomoVis window for the look of the port.

ShotRunner drives the real window over the realistic crops of the DLR-TomoSAR
test tomogram and grabs the whole window (QWidget.grab, menu bar included, no
title bar) at the session's window size after each state worth comparing, plus
the File and Data menus, the Axes dialog and a warning box as separate images.
Grabs land in one flat directory with numbered, descriptive file names.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5 import QtCore, QtWidgets


class ShotRunner:
    """Takes the reference screenshots.

    Attributes:
        session   : TomoVisSession driving the original window.
        out_dir   : Directory receiving the PNG files.
        realistic : Mapping with the "single" (.hd5) and "rgb" (.npy) realistic cube paths.
        logger    : WebLogger for progress and slot exceptions.
        written   : Paths written so far.
    """

    SINGLE_OBLIQUE    = ("30", "40", "12", "330", "0", "0")
    SINGLE_HORIZONTAL = ("10", "100", "0", "380", "0", "0")

    def __init__(self, session, out_dir: Path, realistic: dict, logger) -> None:
        """Stores collaborators and creates the output directory.

        Args:
            session   : TomoVisSession driving the original window.
            out_dir   : Directory receiving the PNG files.
            realistic : Mapping with the "single" and "rgb" realistic cube paths.
            logger    : WebLogger for progress and slot exceptions.
        """

        self.session   = session
        self.out_dir   = out_dir
        self.realistic = realistic
        self.logger    = logger
        self.written   = []
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def act(self, action: str, **args) -> None:
        """Performs one session action and logs any slot exception.

        Args:
            action : Action name understood by TomoVisSession.perform.
            args   : Keyword arguments of the action.
        """

        outcome = self.session.perform(action, args)
        for error in outcome["errors"]:
            self.logger.warning(f"shot step {action}: {error['type']}: {error['message']}")

    def grab(self, name: str) -> None:
        """Saves the whole window as ``<name>.png``.

        Args:
            name : File stem.
        """

        self.session.settle()
        path = self.out_dir / f"{name}.png"
        self.session.window.grab().save(str(path))
        self.written.append(path)

    def grab_menu(self, menu, name: str) -> None:
        """Pops a menu up next to the window, saves it as ``<name>.png`` and closes it.

        Args:
            menu : QMenu to show.
            name : File stem.
        """

        menu.popup(self.session.window.mapToGlobal(QtCore.QPoint(10, 24)))
        self.session.settle()
        path = self.out_dir / f"{name}.png"
        menu.grab().save(str(path))
        menu.hide()
        self.written.append(path)

    def grab_warning(self, name: str) -> None:
        """Builds the "No data" warning box TomoVis shows and saves it as ``<name>.png``.

        Args:
            name : File stem.
        """

        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning, "No data", "There is no data loaded to save.", QtWidgets.QMessageBox.Ok, self.session.window)
        box.show()
        self.session.settle()
        path = self.out_dir / f"{name}.png"
        box.grab().save(str(path))
        box.hide()
        box.deleteLater()
        self.written.append(path)

    def startup(self) -> None:
        """Grabs the empty window on every tab and the menus without data."""

        self.session.open_window()
        self.grab("01_startup_slicer_no_data")
        self.act("tab", index=1)
        self.grab("02_startup_plot_no_data")
        self.act("tab", index=2)
        self.grab("03_startup_profile_no_data")
        self.act("tab", index=3)
        self.grab("04_startup_3d_placeholder")
        self.act("tab", index=0)
        self.grab_menu(self.session.window.fileMenu, "05_menu_file")
        self.grab_menu(self.session.window.importMenu, "06_menu_file_import")
        self.grab_menu(self.session.window.dataMenu, "07_menu_data_no_data")
        self.grab_warning("08_message_no_data_warning")

    def single(self) -> None:
        """Grabs the single-channel states: Slicer, ROI cases, slice mode, colortables, ImageView buttons, Plot, Axes, Profile and 3D."""

        window = self.session.window
        self.act("import", kind="hd5", path=str(self.realistic["single"]))
        self.grab("10_single_loaded_default_roi")
        self.act("set_roi", **dict(zip(("ax", "ay", "angle", "length", "pos_x", "pos_y"), self.SINGLE_OBLIQUE)))
        self.grab("11_single_roi_oblique")
        self.act("set_roi", **dict(zip(("ax", "ay", "angle", "length", "pos_x", "pos_y"), self.SINGLE_HORIZONTAL)))
        self.grab("12_single_roi_horizontal")
        self.act("check", widget="tab1ChkBox", checked=True)
        self.act("value", widget="tab1SpinBox", value=100)
        self.grab("13_single_slice_mode")
        self.act("click", widget="tab1PlayButton")
        self.grab("14_single_slice_playing")
        self.act("click", widget="tab1PlayButton")
        self.act("check", widget="tab1ChkBox", checked=False)
        self.act("set_roi", **dict(zip(("ax", "ay", "angle", "length", "pos_x", "pos_y"), self.SINGLE_OBLIQUE)))
        self.act("combo", widget="tab1ComboBox", index=0)
        self.grab("15_single_colortable_bw_linear")
        self.act("combo", widget="tab1ComboBox", index=4)
        self.grab("16_single_colortable_blue_red_yellow")
        self.act("combo", widget="tab1ComboBox", index=9)

        window.imv1_1.ui.roiBtn.click()
        self.grab("17_single_imageview_roi_button")
        window.imv1_1.ui.roiBtn.click()
        window.imv1_1.ui.menuBtn.click()
        self.grab("18_single_imageview_menu_button")
        window.imv1_1.ui.menuBtn.click()

        self.act("click", widget="tab1PlotButton")
        self.grab("20_plot_half_height")
        self.act("check", widget="tab2ChkBox4", checked=True)
        self.grab("21_plot_full_view")
        self.act("check", widget="tab2ChkBox1", checked=True)
        self.grab("22_plot_normalized")
        self.act("check", widget="tab2ChkBox2", checked=True)
        self.act("value", widget="tab2Slider", value=6)
        self.grab("23_plot_hist_eq_6_bins")
        self.act("check", widget="tab2ChkBox2", checked=False)
        self.act("check", widget="tab2ChkBox3", checked=True)
        self.grab("24_plot_x_line")
        self.act("axes", values={"x_label": "Distance [m]", "z_label": "Height [m]"}, grab=str(self.out_dir / "25_axes_dialog.png"))
        self.written.append(self.out_dir / "25_axes_dialog.png")
        self.grab("26_plot_after_axes")
        self.act("combo", widget="tab2ComboBox", text="viridis")
        self.grab("27_plot_viridis")
        self.act("click", widget="tab2PlotButton")
        self.grab("30_profile_single_normalized")
        self.act("check", widget="tab2ChkBox1", checked=False)
        self.act("click", widget="tab2PlotButton")
        self.grab("31_profile_single_raw")
        self.act("tab", index=3)
        self.grab("40_3d_single_without_pyopengl")
        self.act("tab", index=0)

    def rgb(self, base: int, label: str, shim: bool) -> None:
        """Grabs the pseudo-RGB states: composite, ROI, slice mode, channel menu, each channel, RGB Plot and Profile, 3D.

        Args:
            base  : Number of the first file; the others follow in order.
            label : Word put after the number, "as_is" or "levels_fixed".
            shim  : Whether RgbLevelsShim is enabled for the pass.
        """

        names = ["loaded_default_roi", "roi_oblique", "slice_mode", "menu_data_channel", "red_channel", "green_channel", "blue_channel", "rgb_plot", "rgb_plot_normalized", "rgb_plot_x_line", "rgb_profile", "3d_without_pyopengl"]
        files = {name: f"{base + index}_rgb_{label}_{name}" for index, name in enumerate(names)}

        self.session.levels_shim.enabled = shim
        self.session.open_window()
        window = self.session.window
        self.act("import", kind="npy", path=str(self.realistic["rgb"]))
        self.grab(files["loaded_default_roi"])
        self.act("set_roi", **dict(zip(("ax", "ay", "angle", "length", "pos_x", "pos_y"), self.SINGLE_OBLIQUE)))
        self.grab(files["roi_oblique"])
        self.act("check", widget="tab1ChkBox", checked=True)
        self.act("value", widget="tab1SpinBox", value=100)
        self.grab(files["slice_mode"])
        self.act("check", widget="tab1ChkBox", checked=False)
        self.grab_menu(window.ChMenu, files["menu_data_channel"])
        self.act("channel", mode="Red")
        self.grab(files["red_channel"])
        self.act("channel", mode="Green")
        self.grab(files["green_channel"])
        self.act("channel", mode="Blue")
        self.grab(files["blue_channel"])
        self.act("channel", mode="RGB")
        self.act("click", widget="tab1PlotButton")
        self.grab(files["rgb_plot"])
        self.act("check", widget="tab2ChkBox1", checked=True)
        self.grab(files["rgb_plot_normalized"])
        self.act("check", widget="tab2ChkBox3", checked=True)
        self.grab(files["rgb_plot_x_line"])
        self.act("click", widget="tab2PlotButton")
        self.grab(files["rgb_profile"])
        self.act("tab", index=3)
        self.grab(files["3d_without_pyopengl"])
        self.session.levels_shim.enabled = False

    def run(self) -> list[Path]:
        """Takes every screenshot.

        Returns:
            Paths of the written PNG files.
        """

        self.startup()
        self.single()
        self.rgb(50, "as_is", False)
        self.rgb(70, "levels_fixed", True)
        self.session.close_window()
        self.logger.ok(f"{len(self.written)} screenshots in {self.out_dir}")
        return self.written
