"""Curated catalog of the project's equations for the web UI equation tab.

Each private builder returns one thematic group of LaTeX entries (title, `tex`
source, prose note, and per-symbol variable glossary) describing the maths the
codebase actually implements, from the tomographic forward model through the
processing pipeline that builds the tomogram, interferograms and geometry field.
"""

from __future__ import annotations


class EquationLibrary:
    """Builds the grouped equation catalog rendered by the web UI."""

    def _signal_model(self) -> dict:
        """Returns the signal-model group: forward model, steering, kz and beamformers."""
        return {
            "group" : "Signal Model",
            "blurb" : "How a stack of co-registered SAR passes becomes an elevation power spectrum.",
            "items" : [
                {
                    "title" : "Tomographic observation model",
                    "tex"   : r"\mathbf{y} = \int_{\xi} \gamma(\xi)\,\mathbf{a}(\xi)\,\mathrm{d}\xi + \mathbf{n}",
                    "note"  : "The complex interferometric vector is the steering-weighted integral of reflectivity over elevation, plus noise. The beamformers estimate gamma from the second-order statistics of this model, the steering outer product averaged over a spatial window.",
                    "vars"  : [
                        {"sym": r"\mathbf{y}",      "desc": "complex observation vector over the N_s passes"},
                        {"sym": r"\xi",             "desc": "elevation coordinate (m)"},
                        {"sym": r"\gamma(\xi)",     "desc": "normalised reflectivity along elevation"},
                        {"sym": r"\mathbf{a}(\xi)", "desc": "steering vector built from the per-pass interferometric wavenumbers"},
                        {"sym": r"\mathbf{n}",      "desc": "additive complex noise vector"},
                    ],
                },
                {
                    "title" : "Steering vector element",
                    "tex"   : r"a_i(\xi) = \exp\!\left(j\,\kappa_{z,i}\,\xi\right)",
                    "note"  : "Each pass turns elevation into a unit-modulus phase ramp whose rate is its interferometric wavenumber, defined per pixel by the geometry field or per track by the acquisition geometry.",
                    "vars"  : [
                        {"sym": r"a_i(\xi)",     "desc": "steering element of pass i at elevation xi"},
                        {"sym": r"j",            "desc": "imaginary unit, j^2 = -1"},
                        {"sym": r"\kappa_{z,i}", "desc": "interferometric wavenumber of pass i (rad/m)"},
                        {"sym": r"\xi",          "desc": "elevation coordinate (m)"},
                    ],
                },
                {
                    "title" : "Interferometric wavenumber",
                    "tex"   : r"\kappa_{z,i} = \frac{4\pi}{\lambda}\,\frac{b_{\perp,i}}{r\,\sin\theta}\quad(\text{height}), \qquad \kappa_{z,i} = \frac{4\pi}{\lambda}\,\frac{b_{\perp,i}}{r}\quad(\text{slant})",
                    "note"  : "Phase-to-elevation wavenumber per pass, assembled per pixel from the geometry field (meta/geometry_field.npz) or as one scalar per track from the config slant range and look angle via TomoGeometry. The default 'height' convention divides by sin(theta) so xi is a true vertical height; the 'slant' convention omits it.",
                    "vars"  : [
                        {"sym": r"\kappa_{z,i}", "desc": "interferometric wavenumber of pass i (rad/m)"},
                        {"sym": r"\lambda",      "desc": "radar wavelength (m); config default 0.23, but read from the track parameters when the geometry field is active"},
                        {"sym": r"b_{\perp,i}",  "desc": "perpendicular baseline of pass i (m)"},
                        {"sym": r"r",            "desc": "slant range at the pixel's range bin (m)"},
                        {"sym": r"\theta",       "desc": "look angle at the pixel's range bin (rad)"},
                    ],
                },
                {
                    "title" : "Per-pixel scene geometry",
                    "tex"   : r"b_{\perp,i} = b_{h,i}\cos\theta + b_{v,i}\sin\theta, \qquad b_{\cdot,i} = p_{\cdot,i} - p_{\cdot,0}, \qquad \theta = \arccos\!\left(\frac{h}{r}\right)",
                    "note"  : "The perpendicular baseline projects each pass's horizontal and vertical offset from the reference track onto the look direction; the offsets vary along azimuth while the look angle and slant range vary along range. The look angle is recovered per range bin from the sensor height above terrain h = h0 - terrain over the slant range, and the build rejects non-physical h that would give a zero look angle and infinite kz.",
                    "vars"  : [
                        {"sym": r"b_{\perp,i}",      "desc": "perpendicular baseline of pass i (m)"},
                        {"sym": r"b_{h,i}, b_{v,i}", "desc": "horizontal / vertical baseline of pass i relative to the reference pass (m)"},
                        {"sym": r"p_{\cdot,i}",      "desc": "horizontal or vertical track position of pass i along azimuth (m)"},
                        {"sym": r"\theta",           "desc": "look angle from vertical (rad)"},
                        {"sym": r"h",                "desc": "sensor height above terrain, h0 - terrain (m)"},
                        {"sym": r"r",                "desc": "slant range at the range bin (m)"},
                    ],
                },
                {
                    "title" : "Capon beamformer",
                    "tex"   : r"\hat{\gamma}_{\text{Capon}}(\xi) = \frac{1}{\mathbf{a}^{H}(\xi)\,\hat{\mathbf{R}}^{-1}\,\mathbf{a}(\xi)}",
                    "note"  : "Minimum-variance distortionless response estimate of the elevation spectrum from the sample covariance; the default PyRat beamforming method.",
                    "vars"  : [
                        {"sym": r"\hat{\gamma}_{\text{Capon}}(\xi)", "desc": "estimated reflectivity at elevation xi"},
                        {"sym": r"\mathbf{a}(\xi)",                  "desc": "steering vector at elevation xi"},
                        {"sym": r"\mathbf{a}^{H}",                   "desc": "Hermitian (conjugate) transpose of the steering vector"},
                        {"sym": r"\hat{\mathbf{R}}",                 "desc": "sample covariance estimated over a spatial window"},
                    ],
                },
                {
                    "title" : "Elevation axis",
                    "tex"   : r"x_h = x_{\min} + h\cdot\frac{x_{\max}-x_{\min}}{H-1}, \qquad h = 0,\dots,H-1, \qquad \Delta\xi = \frac{x_{\max}-x_{\min}}{H-1}",
                    "note"  : "Uniform grid of H elevation bins spanning the configured height range of the beamformed tomogram.",
                    "vars"  : [
                        {"sym": r"x_h",                "desc": "elevation value at bin index h (m)"},
                        {"sym": r"h",                  "desc": "elevation bin index"},
                        {"sym": r"x_{\min}, x_{\max}", "desc": "height range bounds, default (-20 m, 80 m)"},
                        {"sym": r"H",                  "desc": "number of elevation bins"},
                        {"sym": r"\Delta\xi",          "desc": "elevation bin spacing (m)"},
                    ],
                },
            ],
        }

    def _processing(self) -> dict:
        """Returns the processing group: SLC cropping, tomogram beamforming, interferograms and geometry field."""
        return {
            "group" : "Processing",
            "blurb" : "From F-SAR SLC data to the beamformed tomogram, DEM-deramped interferograms, and the per-pixel geometry field, dispatched across parallel PyRat workers.",
            "items" : [
                {
                    "title" : "Azimuth crop subdivision",
                    "tex"   : r"M = \left\lceil \frac{W_{az}}{W_{\max}} \right\rceil, \qquad s_m = a_{\mathrm{start}} + m\,W_{\max}, \qquad e_m = \min\!\left(s_m + W_{\max},\, a_{\mathrm{end}}\right)",
                    "note"  : "The azimuth crop is divided into M non-overlapping subsections, one isolated PyRat subprocess each.",
                    "vars"  : [
                        {"sym": r"M",                                    "desc": "number of subsections"},
                        {"sym": r"W_{az}",                               "desc": "total azimuth width in lines"},
                        {"sym": r"W_{\max}",                             "desc": "max azimuth lines per worker, default 1000"},
                        {"sym": r"m",                                    "desc": "subsection index, 0 to M-1"},
                        {"sym": r"[s_m, e_m)",                           "desc": "azimuth bounds of subsection m"},
                        {"sym": r"a_{\mathrm{start}}, a_{\mathrm{end}}", "desc": "azimuth crop bounds (absolute lines)"},
                    ],
                },
                {
                    "title" : "Worker auto-sizing",
                    "tex"   : r"P^{\star} = \arg\min_{1 \le P \le \min(M,\,B)} \left\lceil \frac{M}{P} \right\rceil, \qquad T = \max\!\left(1,\ \min\!\left(16,\ \left\lfloor B/P \right\rfloor\right)\right), \qquad B = \max\!\left(1,\ \lfloor f_{\mathrm{effort}}\,C \rfloor\right)",
                    "note"  : "Without explicit overrides the launched worker count minimises the number of sequential job waves ceil(M/P); because the loop scans workers ascending and only replaces a tied plan when it has strictly more threads, it settles on the fewest workers that still reach the minimum wave count, so wave-count ties resolve toward more threads per worker (not more workers). Each PyRat worker then takes floor(B/P) threads, capped at 16, out of the effort core budget B: low 25%, medium 50%, high 80% of the scheduler-affinity-visible cores. Setting tomogram_workers or pyrat_threads pins that value and lets the other adapt to the remaining budget.",
                    "vars"  : [
                        {"sym": r"P^{\star}",           "desc": "process-pool workers actually launched"},
                        {"sym": r"T",                   "desc": "threads per PyRat subprocess, floored at 1 and capped at 16"},
                        {"sym": r"M",                   "desc": "number of subsections (one job each)"},
                        {"sym": r"B",                   "desc": "core budget max(1, floor(effort fraction x cores))"},
                        {"sym": r"f_{\mathrm{effort}}", "desc": "effort fraction: low 0.25, medium 0.5, high 0.8"},
                        {"sym": r"C",                   "desc": "CPU cores visible via scheduler affinity (fallback os.cpu_count)"},
                    ],
                },
                {
                    "title" : "Subsection concatenation",
                    "tex"   : r"T_{\mathrm{comb}} = \mathrm{concat}\!\left[T_0, \dots, T_{M-1}\right]_{\mathrm{axis}=1}, \qquad \mathrm{DEM}_{\mathrm{comb}} = \mathrm{concat}\!\left[\mathrm{DEM}_0, \dots, \mathrm{DEM}_{M-1}\right]_{\mathrm{axis}=0}",
                    "note"  : "Per-worker HDF5 outputs are reassembled along azimuth in two passes: shapes first, then slice-copies into pre-allocated buffers.",
                    "vars"  : [
                        {"sym": r"T_m",                          "desc": "tomogram of subsection m, shape (H, W_m, R_g)"},
                        {"sym": r"T_{\mathrm{comb}}",            "desc": "combined tomogram, shape (H, SUM W_m, R_g)"},
                        {"sym": r"\mathrm{DEM}_m",               "desc": "DEM of subsection m, shape (W_m, R_g)"},
                        {"sym": r"\mathrm{DEM}_{\mathrm{comb}}", "desc": "combined DEM, shape (SUM W_m, R_g)"},
                        {"sym": r"M",                            "desc": "number of subsections"},
                    ],
                },
                {
                    "title" : "Right-looking geometry gate",
                    "tex"   : r"\mathrm{antdir}_i > 0 \quad \forall\, i \in \{0, 1, \dots, N_s\}",
                    "note"  : "During the interferogram stage every pass's antenna-direction flag is read from its STEP pp_*.xml and checked: any track with antdir <= 0 is left-looking and aborts the run, because the downstream kz / steering geometry assumes a right-looking acquisition and left-looking data would carry sign-flipped geometry (TrackParameters.validate_right_looking, invoked by TrackParameterCollector.collect during _extract_parameters, and again inside the geometry-field build).",
                    "vars"  : [
                        {"sym": r"\mathrm{antdir}_i", "desc": "antenna-direction (look-side) flag of pass i from pp_*.xml; > 0 is right-looking"},
                        {"sym": r"i",                 "desc": "pass index, 0 = master (reference)"},
                        {"sym": r"N_s",               "desc": "number of secondary passes (master is index 0)"},
                    ],
                },
                {
                    "title" : "DEM-phase deramping",
                    "tex"   : r"\tilde{s}_i = s_i\cdot\exp\!\left(j\,\phi_{\mathrm{DEM},i}\right)",
                    "note"  : "The secondary SLC is phase-rotated by the DEM-predicted phase (multiplied by exp(+j*phi_DEM)); the subsequent master x conjugate-deramped-secondary product then cancels the terrain topographic phase, leaving the residual sub-DEM elevation structure.",
                    "vars"  : [
                        {"sym": r"\tilde{s}_i",           "desc": "DEM-deramped secondary SLC of pass i"},
                        {"sym": r"s_i",                   "desc": "co-registered secondary SLC value"},
                        {"sym": r"j",                     "desc": "imaginary unit, j^2 = -1"},
                        {"sym": r"\phi_{\mathrm{DEM},i}", "desc": "DEM phase of pass i from PyRat (radians)"},
                    ],
                },
                {
                    "title" : "Amplitude-weighted complex interferogram",
                    "tex"   : r"\phi_i = A_i\cdot\frac{s_0\,\overline{\tilde{s}_i}}{\left|s_0\,\overline{\tilde{s}_i}\right|}, \qquad A_i = \min\!\left(|s_i|,\,A_{\max}\right)",
                    "note"  : "Unit-phasor normalisation removes inter-pass amplitude variation while preserving coherence; the clipped secondary amplitude is reintroduced as a signal-to-noise proxy. A 1e-30 stabiliser guards the denominator in code.",
                    "vars"  : [
                        {"sym": r"\phi_i",                 "desc": "complex interferogram of pass i"},
                        {"sym": r"s_0",                    "desc": "master (primary) SLC value"},
                        {"sym": r"\overline{\tilde{s}_i}", "desc": "complex conjugate of the deramped secondary"},
                        {"sym": r"A_i",                    "desc": "clipped secondary amplitude weight"},
                        {"sym": r"|s_i|",                  "desc": "secondary SLC magnitude"},
                        {"sym": r"A_{\max}",               "desc": "max_amplitude_clip = 1.25"},
                    ],
                },
                {
                    "title" : "Per-pixel geometry field",
                    "tex"   : r"\theta_g = \arccos\!\left(\mathrm{clip}\!\left(\frac{h_0 - h_{\mathrm{ter}}}{r_g},\ -1,\ 1\right)\right), \qquad b^{\mathrm{h}}_{i} = H_i - H_0, \qquad b^{\mathrm{v}}_{i} = V_i - V_0",
                    "note"  : "The third and final processing stage builds and saves the per-pixel geometry field (geometry_field.npz). The per-range-sample look angle is taken from the reference track's sensor height above terrain over its cropped slant-range vector; the per-track horizontal and vertical baselines are the antenna-position profiles taken relative to the reference (index 0) track, so the reference baseline is zero. The build re-runs the right-looking gate and aborts if the height above terrain is non-positive or not below the nearest slant range (which would give a zero look angle and infinite kz). Only theta, r and the baselines are stored; the vertical wavenumber kz = 4*pi*b_perp/(lambda*r*sin theta) with b_perp = b_h*cos theta + b_v*sin theta follows from them.",
                    "vars"  : [
                        {"sym": r"\theta_g",                               "desc": "look angle at range sample g (radians), from the reference track"},
                        {"sym": r"h_0",                                    "desc": "reference-track sensor altitude"},
                        {"sym": r"h_{\mathrm{ter}}",                       "desc": "reference-track terrain height"},
                        {"sym": r"r_g",                                    "desc": "slant range at sample g from the reference track's range vector (cropped to the range window)"},
                        {"sym": r"b^{\mathrm{h}}_{i}, b^{\mathrm{v}}_{i}", "desc": "horizontal / vertical baseline of track i relative to the reference (index 0) track"},
                        {"sym": r"H_i, V_i",                               "desc": "horizontal / vertical antenna-position profile of track i (H_0, V_0 = reference)"},
                    ],
                },
            ],
        }

    def collect(self) -> list[dict]:
        """Returns every equation group in presentation order."""
        return [
            self._signal_model(),
            self._processing(),
        ]
