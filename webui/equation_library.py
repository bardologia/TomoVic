"""Curated catalog of the project's equations for the web UI equation tab.

Each private builder returns one thematic group of LaTeX entries (title, `tex`
source, prose note, and per-symbol variable glossary) describing the maths the
codebase actually implements, from the tomographic forward model through
processing, parameter extraction, dataset construction, training and inference.
"""

from __future__ import annotations


class EquationLibrary:
    """Builds the grouped equation catalog rendered by the web UI."""

    def _signal_model(self) -> dict:
        """Returns the signal-model group: forward model, steering, kz and beamformers."""
        return {
            "group" : "Signal Model",
            "blurb" : "How a stack of co-registered SAR passes becomes an elevation power spectrum, and the Gaussian mixture that summarises it.",
            "items" : [
                {
                    "title" : "Tomographic observation model",
                    "tex"   : r"\mathbf{y} = \int_{\xi} \gamma(\xi)\,\mathbf{a}(\xi)\,\mathrm{d}\xi + \mathbf{n}",
                    "note"  : "The complex interferometric vector is the steering-weighted integral of reflectivity over elevation, plus noise. The code realises the forward map as a discrete sum sum_xi a(xi)*gamma(xi)*dx (synthesise_track) and the second-order statistics via the steering outer product.",
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
                    "note"  : "Each pass turns elevation into a unit-modulus phase ramp whose rate is its interferometric wavenumber; the code builds it as torch.polar(1, kz*xi) with kz defined separately, per-pixel when the geometry field is active and per-track when it is not.",
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
                    "note"  : "Phase-to-elevation wavenumber per pass. When a physics-geometry loss term is active it is assembled per pixel from the geometry field (meta/geometry_field.npz, kz(convention) sliced per region into the batch kz_map); otherwise it collapses to one scalar per track from the config slant range and look angle via TomoGeometry. The default 'height' convention divides by sin(theta) so xi is a true vertical height; the 'slant' convention omits it.",
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
                    "note"  : "Uniform grid of H elevation bins spanning the configured height range; the bin spacing recurs in fitting bounds and peak distances.",
                    "vars"  : [
                        {"sym": r"x_h",                "desc": "elevation value at bin index h (m)"},
                        {"sym": r"h",                  "desc": "elevation bin index"},
                        {"sym": r"x_{\min}, x_{\max}", "desc": "height range bounds, default (-20 m, 80 m)"},
                        {"sym": r"H",                  "desc": "number of elevation bins"},
                        {"sym": r"\Delta\xi",          "desc": "elevation bin spacing (m)"},
                    ],
                },
                {
                    "title" : "Gaussian mixture approximation",
                    "tex"   : r"\hat{\gamma}(\xi) = \sum_{k=1}^{K} a_k\,\exp\!\left(-\frac{(\xi-\mu_k)^2}{2\sigma_k^2}\right)",
                    "note"  : "Each per-pixel elevation spectrum is approximated by K Gaussians, one per scattering layer; these parameters are the supervised target.",
                    "vars"  : [
                        {"sym": r"\hat{\gamma}(\xi)", "desc": "modelled elevation power spectrum"},
                        {"sym": r"\xi",               "desc": "elevation coordinate (m)"},
                        {"sym": r"K",                 "desc": "number of Gaussian components"},
                        {"sym": r"a_k",               "desc": "amplitude (peak reflectivity) of component k"},
                        {"sym": r"\mu_k",             "desc": "mean elevation of component k (m)"},
                        {"sym": r"\sigma_k",          "desc": "elevation spread of component k (m)"},
                    ],
                },
                {
                    "title" : "Per-pixel parameter vector",
                    "tex"   : r"\theta = [\,a_1, \mu_1, \sigma_1,\; a_2, \mu_2, \sigma_2,\; \dots,\; a_{K}, \mu_{K}, \sigma_{K}\,] \in \mathbb{R}^{3K}",
                    "note"  : "Interleaved layout used everywhere: the GT array, the model output channels, and the loss (a at 3k, mu at 3k+1, sigma at 3k+2). K is derived from the parameter run's k_max (not a user knob), amplitude is clamped to a floor of 0, and a slot counts as active when its amplitude exceeds amp_zero_thr = 1e-4.",
                    "vars"  : [
                        {"sym": r"\theta",               "desc": "per-pixel parameter vector"},
                        {"sym": r"a_k, \mu_k, \sigma_k", "desc": "amplitude, mean elevation, spread of slot k"},
                        {"sym": r"K",                    "desc": "number of Gaussian slots, K = k_max from param_extraction_meta.json (default 5)"},
                        {"sym": r"3K",                   "desc": "channels per pixel, three parameters per slot"},
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
                    "note"  : "During the interferogram stage every pass's antenna-direction flag is read from its STEP pp_*.xml and checked: any track with antdir <= 0 is left-looking and aborts the run, because the downstream kz / steering geometry assumes a right-looking acquisition and left-looking data would train against sign-flipped physics (TrackParameters.validate_right_looking, invoked by TrackParameterCollector.collect during _extract_parameters, and again inside the geometry-field build).",
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
                    "note"  : "The third and final processing stage builds and saves the per-pixel geometry field (geometry_field.npz) that the physics loss later consumes. The per-range-sample look angle is taken from the reference track's sensor height above terrain over its cropped slant-range vector; the per-track horizontal and vertical baselines are the antenna-position profiles taken relative to the reference (index 0) track, so the reference baseline is zero. The build re-runs the right-looking gate and aborts if the height above terrain is non-positive or not below the nearest slant range (which would give a zero look angle and infinite kz). Only theta, r and the baselines are stored: the physics-loss vertical wavenumber kz = 4*pi*b_perp/(lambda*r*sin theta) with b_perp = b_h*cos theta + b_v*sin theta is formed later at training time (documented under Training loss).",
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

    def _param_extraction(self) -> dict:
        """Returns the parameter-extraction group: profile conditioning, peak initialisation, masked Adam fit, best-K selection and diagnostics."""
        return {
            "group" : "Param Extraction",
            "blurb" : "Every step of the three-phase per-pixel fit: profile conditioning, CPU prominence-peak initialisation shared across model orders, JAX GPU masked Adam (widths by default, optionally amplitudes and means), penalised best-K selection, and the R2, peak-to-floor contrast and K-margin diagnostic maps.",
            "items" : [
                {
                    "title" : "Profile magnitude and relative threshold",
                    "tex"   : r"P_h = |T_h|, \qquad P_h \leftarrow P_h \cdot \mathbf{1}\!\left[\,P_h > t_f \cdot \max_h P_h\,\right]",
                    "note"  : "Each elevation profile is the tomogram magnitude; samples below a per-pixel relative floor are zeroed before fitting, applied only when threshold_factor > 0 (ProfilePreprocessor.apply in tools/data/preprocessing.py, called from sigma/extractor.py SigmaFittingExtractor._load_batch on the raw magnitude, max taken over the elevation axis).",
                    "vars"  : [
                        {"sym": r"P_h",               "desc": "profile value at elevation bin h"},
                        {"sym": r"T_h",               "desc": "tomogram value at bin h (per pixel)"},
                        {"sym": r"t_f",               "desc": "threshold_factor = 0.25"},
                        {"sym": r"\mathbf{1}[\cdot]", "desc": "indicator: 1 if the condition holds, else 0"},
                        {"sym": r"\max_h P_h",        "desc": "per-pixel profile maximum"},
                    ],
                },
                {
                    "title" : "Elevation truncation",
                    "tex"   : r"P_h = 0 \quad \forall\, h \geq h_{\mathrm{trunc}}",
                    "note"  : "Samples beyond the truncation index are zeroed, discarding the upper part of the elevation axis known to carry no signal (only when truncation_index < H).",
                    "vars"  : [
                        {"sym": r"P_h",                "desc": "profile value at elevation bin h"},
                        {"sym": r"h",                  "desc": "elevation bin index"},
                        {"sym": r"h_{\mathrm{trunc}}", "desc": "truncation_index = 170"},
                    ],
                },
                {
                    "title" : "Per-pixel normalisation",
                    "tex"   : r"s = \max_h P_h, \qquad \tilde{\gamma}_h = \frac{P_h}{s}",
                    "note"  : "The profile is normalised by its own maximum so the loss surface is independent of absolute backscatter. Pixels whose maximum is below the activity threshold (1e-3) are skipped entirely (their scale is treated as 1).",
                    "vars"  : [
                        {"sym": r"s",                "desc": "per-pixel scale, reapplied to amplitudes at the end"},
                        {"sym": r"P_h",              "desc": "conditioned profile at bin h"},
                        {"sym": r"\tilde{\gamma}_h", "desc": "normalised profile at bin h"},
                    ],
                },
                {
                    "title" : "Prominence gate and inter-peak distance",
                    "tex"   : r"\mathrm{prom}(p) \geq p_{\mathrm{frac}} \cdot \max_h P_h, \qquad |p_i - p_j| \geq d_{\min}",
                    "note"  : "scipy.signal.find_peaks runs directly on the raw (un-smoothed) profile and keeps a peak only if its topographic prominence exceeds a fraction of the profile maximum and it is at least d_min samples from any other accepted peak; accepted peaks are then sorted by descending prominence (sigma/initialiser.py PeakInitialiser).",
                    "vars"  : [
                        {"sym": r"\mathrm{prom}(p)",  "desc": "height of peak p above its lowest enclosing contour"},
                        {"sym": r"p_{\mathrm{frac}}", "desc": "prominence_frac = 0.05"},
                        {"sym": r"P_h",               "desc": "raw profile"},
                        {"sym": r"p_i, p_j",          "desc": "accepted peak positions (bins)"},
                        {"sym": r"d_{\min}",          "desc": "minimum inter-peak distance (samples)"},
                    ],
                },
                {
                    "title" : "Width scale, initial guess, and minimum distance",
                    "tex"   : r"\sigma_{\mathrm{base}} = \max\!\left(2\,\Delta\xi,\ \frac{x_{\max}-x_{\min}}{8K}\right), \qquad \sigma_{\mathrm{guess}} = \frac{\sigma_{\mathrm{base}}}{\max(D_\sigma,\,10^{-6})}, \qquad d_{\min} = \max\!\left(1,\ \left\lfloor \sigma_{\mathrm{base}}/\Delta\xi \right\rfloor\right)",
                    "note"  : "Initialisation is run once at K = k_max: a span-derived width scale sets the peak-separation distance and every slot receives the same initial width (that scale divided by sigma_init_divisor, itself floored at 1e-6 to avoid division by zero). Each candidate model order then reuses the first K of these shared components rather than re-initialising per K, and the same initialisation is shared by every fit mode of the sweep group (sigma/initialiser.py PeakInitialiser.run, sliced in sigma/extractor.py _fit_batch).",
                    "vars"  : [
                        {"sym": r"\sigma_{\mathrm{base}}",  "desc": "span-derived width scale (m)"},
                        {"sym": r"\sigma_{\mathrm{guess}}", "desc": "initial spread assigned to every slot (m)"},
                        {"sym": r"D_\sigma",                "desc": "sigma_init_divisor = 4.0"},
                        {"sym": r"\Delta\xi",               "desc": "elevation bin spacing (m)"},
                        {"sym": r"x_{\min}, x_{\max}",      "desc": "elevation axis bounds (m)"},
                        {"sym": r"K",                       "desc": "k_max (init is run once at the maximum order)"},
                        {"sym": r"d_{\min}",                "desc": "minimum inter-peak distance (samples)"},
                    ],
                },
                {
                    "title" : "Top-K selection and residual supplement",
                    "tex"   : r"\mathrm{idxs} = \operatorname{top}K_{\mathrm{prom}}(\mathrm{peaks}), \qquad e = \operatorname{argmax}_h R_h, \quad R_{[e - d_{\min},\, e + d_{\min}]} \leftarrow 0",
                    "note"  : "The shared k_max initialisation fills K = k_max slots and each candidate order takes the first K. With k_max or more peaks, the most prominent win; with fewer, maxima of the residual profile fill the remaining slots, each zeroing a suppression window around itself (sigma/initialiser.py PeakInitialiser).",
                    "vars"  : [
                        {"sym": r"\mathrm{idxs}",  "desc": "selected peak indices, one per slot"},
                        {"sym": r"\mathrm{peaks}", "desc": "detected peak positions"},
                        {"sym": r"K",              "desc": "slots to fill (k_max in the shared init)"},
                        {"sym": r"R_h",            "desc": "residual profile with accepted peaks zeroed"},
                        {"sym": r"e",              "desc": "next supplemental index (residual maximum)"},
                        {"sym": r"d_{\min}",       "desc": "suppression half-width (samples)"},
                    ],
                },
                {
                    "title" : "Flat-profile fallback",
                    "tex"   : r"\mathrm{idxs} = \mathrm{linspace}(0,\, H{-}1,\, K), \qquad a_g = \max\!\left(P_{i_g},\ 10^{-10}\right)",
                    "note"  : "Profiles with no detectable signal (raw maximum below 1e-10) receive K equally spaced initialisations; the same linspace fallback also applies when find_peaks returns zero peaks. Amplitudes are floored at 1e-10 to keep gradients alive.",
                    "vars"  : [
                        {"sym": r"\mathrm{idxs}", "desc": "K equally spaced bin indices"},
                        {"sym": r"H",             "desc": "number of elevation bins"},
                        {"sym": r"K",             "desc": "slots to fill"},
                        {"sym": r"a_g",           "desc": "initial amplitude of slot g"},
                        {"sym": r"P",             "desc": "raw profile"},
                        {"sym": r"i_g",           "desc": "selected peak index of slot g"},
                    ],
                },
                {
                    "title" : "Discrete mixture (shared forward model)",
                    "tex"   : r"\hat{\gamma}(x_h) = \sum_{k=1}^{K} a_k\,\exp\!\left(-\frac{(x_h-\mu_k)^2}{2\sigma_k^2}\right)",
                    "note"  : "The single reconciled convention in tools/data/gaussians.py (GaussianMixture): the R2 map calls evaluate_slice, while the JAX fitting kernel (sigma/kernels.py SigmaScan.per_pixel_loss) is a separate reimplementation with the identical guards and also produces the per-pixel best-K MSE on the GPU. Guards: sigma floored at 1e-6, exponent clipped to [-100, 0].",
                    "vars"  : [
                        {"sym": r"\hat{\gamma}(x_h)", "desc": "reconstructed mixture at sample x_h"},
                        {"sym": r"x_h",               "desc": "h-th elevation sample (m)"},
                        {"sym": r"K",                 "desc": "number of components"},
                        {"sym": r"a_k",               "desc": "amplitude of component k"},
                        {"sym": r"\mu_k",             "desc": "mean elevation of component k (m)"},
                        {"sym": r"\sigma_k",          "desc": "spread of component k (m)"},
                    ],
                },
                {
                    "title" : "GPU amplitude normalisation",
                    "tex"   : r"a_k^{\mathrm{norm}} = a_k^{\mathrm{raw}} / s",
                    "note"  : "Peak amplitudes detected on the raw profile are divided by the per-pixel scale so the GPU fit operates entirely on normalised profiles.",
                    "vars"  : [
                        {"sym": r"a_k^{\mathrm{norm}}", "desc": "amplitude on the normalised profile scale"},
                        {"sym": r"a_k^{\mathrm{raw}}",  "desc": "amplitude detected on the raw profile"},
                        {"sym": r"s",                   "desc": "per-pixel profile maximum"},
                    ],
                },
                {
                    "title" : "Phase 2 — fitting objective",
                    "tex"   : r"\mathcal{L} = \frac{1}{H}\sum_{h=1}^{H}\left(\sum_{k=1}^{K} a_k\,\exp\!\left(-\frac{(x_h-\mu_k)^2}{2\sigma_k^2}\right) - \tilde{\gamma}(x_h)\right)^2, \qquad (g_a, g_\mu, g_\sigma) = \nabla_{(a,\mu,\sigma)}\mathcal{L}",
                    "note"  : "Per-pixel mean squared error between the mixture and the normalised profile, vectorised over pixels with jax.vmap and differentiated w.r.t. amplitudes, means and widths by jax.value_and_grad(argnums=(0,1,2)); each gradient is then multiplied by its fit_amplitude / fit_mean / fit_sigma mask, so any composition of the three parameter groups can be fitted. The default composition frees only the widths (sigma/kernels.py SigmaScan).",
                    "vars"  : [
                        {"sym": r"\mathcal{L}",         "desc": "per-pixel mean squared fit error"},
                        {"sym": r"\sigma",              "desc": "width of component k (free only when fit_sigma on, the default)"},
                        {"sym": r"a_k",                 "desc": "amplitude of component k (free only when fit_amplitude on)"},
                        {"sym": r"\mu_k",               "desc": "mean elevation of component k (free only when fit_mean on)"},
                        {"sym": r"x_h",                 "desc": "h-th elevation sample (m)"},
                        {"sym": r"\tilde{\gamma}(x_h)", "desc": "normalised measured profile"},
                        {"sym": r"H",                   "desc": "number of elevation samples"},
                        {"sym": r"K",                   "desc": "number of components"},
                    ],
                },
                {
                    "title" : "Adam moment estimates (parameter fit)",
                    "tex"   : r"m_t = \beta_1 m_{t-1} + (1-\beta_1)\,g_t, \qquad v_t = \beta_2 v_{t-1} + (1-\beta_2)\,g_t^2, \qquad g_t = \mathbf{1}_\theta \cdot \nabla_{\theta}\mathcal{L}",
                    "note"  : "Independent first and second moment estimates are kept for each of amplitudes, means and widths and updated every step; every gradient is pre-masked by its fit toggle, so the moments of frozen parameter groups stay zero. The whole optimisation is a jax.lax.scan over T steps compiled into a single XLA computation (sigma/kernels.py SigmaScan).",
                    "vars"  : [
                        {"sym": r"m_t",               "desc": "first moment estimate at step t"},
                        {"sym": r"v_t",               "desc": "second moment estimate at step t"},
                        {"sym": r"g_t",               "desc": "masked gradient of the fit loss w.r.t. the free parameter"},
                        {"sym": r"\theta",            "desc": "a free parameter (amplitude, mean or width)"},
                        {"sym": r"\mathbf{1}_\theta", "desc": "per-group fit mask (0 or 1 for each of sigma, amp, mu)"},
                        {"sym": r"t",                 "desc": "optimisation step, 1 to T"},
                        {"sym": r"\beta_1",           "desc": "adam_b1 = 0.95"},
                        {"sym": r"\beta_2",           "desc": "adam_b2 = 0.999"},
                        {"sym": r"T",                 "desc": "adam_steps = 3000"},
                    ],
                },
                {
                    "title" : "Adam update (parameter fit)",
                    "tex"   : r"\hat{m}_t = \frac{m_t}{1-\beta_1^t}, \qquad \hat{v}_t = \frac{v_t}{1-\beta_2^t}, \qquad \theta_t = \theta_{t-1} - \eta\,\frac{\hat{m}_t}{\sqrt{\hat{v}_t} + \epsilon}",
                    "note"  : "Bias-corrected Adam step applied to every free parameter; after each update amplitudes are clamped to >=0, means to [x_min, x_max], and widths to [dxi, (x_max - x_min)/2] - one elevation bin to half the elevation span (sigma/kernels.py SigmaScan, sigma bounds set in sigma/extractor.py).",
                    "vars"  : [
                        {"sym": r"\theta_t",             "desc": "free-parameter value after step t"},
                        {"sym": r"\hat{m}_t, \hat{v}_t", "desc": "bias-corrected first and second moments"},
                        {"sym": r"\beta_1^t, \beta_2^t", "desc": "decay factors to the power t"},
                        {"sym": r"\eta",                 "desc": "adam_lr = 0.2"},
                        {"sym": r"\epsilon",             "desc": "Adam stability, 1e-8"},
                    ],
                },
                {
                    "title" : "Phase 3 — penalised score per K",
                    "tex"   : r"\mathrm{MSE}_K = \frac{1}{H}\sum_{h}\left(\hat{\gamma}_K(x_h) - \tilde{\gamma}(x_h)\right)^2, \qquad \mathrm{pen}_K = \mathrm{MSE}_K + \lambda_K \cdot K",
                    "note"  : "Each extra component must buy at least lambda_k of normalised MSE, so the budget is spent only when the profile is genuinely multi-layered; the per-pixel MSE comes straight from the GPU fit kernel (sigma/kernels.py SigmaScan.adam_scan final forward pass), BestKSelector.score assembles it per K, and the lambda_k*K penalty is applied per lambda value in BestKSelector.select, so a lambda sweep reuses the same fits.",
                    "vars"  : [
                        {"sym": r"\mathrm{MSE}_K",      "desc": "fit error of the K-component model"},
                        {"sym": r"\hat{\gamma}_K(x_h)", "desc": "K-component reconstruction at sample x_h"},
                        {"sym": r"\tilde{\gamma}(x_h)", "desc": "normalised measured profile"},
                        {"sym": r"H",                   "desc": "number of elevation samples"},
                        {"sym": r"\mathrm{pen}_K",      "desc": "penalised score of model order K"},
                        {"sym": r"\lambda_K",           "desc": "per-component complexity penalty, lambda_k = 1e-2"},
                    ],
                },
                {
                    "title" : "Best-K selection and amplitude rescale",
                    "tex"   : r"K^* = \operatorname*{arg\,min}_{K \in \{1,\dots,K_{\max}\}} \mathrm{pen}_K, \qquad a_k^{\mathrm{out}} = a_k^{\mathrm{norm}} \cdot s",
                    "note"  : "The winning K's parameters are written into the interleaved output vector (amp, mu, sigma per slot); slots beyond K* stay zero. Amplitudes return to the raw scale.",
                    "vars"  : [
                        {"sym": r"K^*",                "desc": "selected number of active components"},
                        {"sym": r"K_{\max}",           "desc": "k_max = 5"},
                        {"sym": r"\mathrm{pen}_K",     "desc": "penalised score of model order K"},
                        {"sym": r"a_k^{\mathrm{out}}", "desc": "output amplitude on the raw scale"},
                        {"sym": r"s",                  "desc": "per-pixel profile maximum"},
                    ],
                },
                {
                    "title" : "Component ordering by mean elevation",
                    "tex"   : r"\kappa_k = \begin{cases} \mu_k & a_k > 10^{-3} \\ +\infty & \text{otherwise} \end{cases}, \qquad \pi = \operatorname{argsort}_k\,\kappa_k",
                    "note"  : "After fitting, active components are sorted by ascending mu and inactive slots pushed last (gaussians.py GaussianSlotSorter.by_mean), giving GT a canonical storage order; the downstream training loss is permutation-invariant, matching predictions to these GT slots by optimal assignment.",
                    "vars"  : [
                        {"sym": r"\kappa_k", "desc": "sort key of slot k"},
                        {"sym": r"\mu_k",    "desc": "mean elevation of slot k (m)"},
                        {"sym": r"a_k",      "desc": "amplitude of slot k"},
                        {"sym": r"\pi",      "desc": "resulting slot permutation"},
                    ],
                },
                {
                    "title" : "Fit quality map",
                    "tex"   : r"R^2(a,r) = 1 - \frac{\sum_{h=1}^{H}\big(\hat{\gamma}(x_h) - \gamma(x_h)\big)^2}{\sum_{h=1}^{H}\big(\gamma(x_h) - \bar{\gamma}\big)^2 + \varepsilon}",
                    "note"  : "Per-pixel coefficient of determination over the elevation axis against the thresholded and truncated profile; the reconstruction is built one elevation slice at a time (GaussianMixture.evaluate_slice) and scored by R2.pixel_map with an epsilon = 1e-12 denominator stabiliser (param_extraction/metrics.py FittingMetricsCalculator, tools/metrics/scoring.py).",
                    "vars"  : [
                        {"sym": r"R^2(a,r)",          "desc": "fit quality at azimuth a, range r"},
                        {"sym": r"\hat{\gamma}(x_h)", "desc": "reconstructed mixture at sample x_h"},
                        {"sym": r"\gamma(x_h)",       "desc": "thresholded/truncated tomogram magnitude at x_h"},
                        {"sym": r"\bar{\gamma}",      "desc": "per-pixel mean over elevation"},
                        {"sym": r"\varepsilon",       "desc": "R2.EPSILON = 1e-12 denominator stabiliser"},
                        {"sym": r"H",                 "desc": "number of elevation samples"},
                    ],
                },
                {
                    "title" : "Peak-to-floor contrast (dB) map",
                    "tex"   : r"C(a,r) = 10\,\log_{10}\!\frac{\max_h |T_h|}{\frac{1}{m}\sum_{h \in \mathcal{F}} |T_h|}, \qquad m = \max\!\left(1,\ \mathrm{round}(f\,H)\right)",
                    "note"  : "An uncalibrated per-pixel contrast proxy: the profile maximum over the mean of the m lowest-amplitude elevation bins, in decibels; numerator and denominator are floored at 1e-12 and pixels with a non-positive peak or floor are NaN. It is correlated against R2 (Pearson and Spearman) and conditioned on the selected K in the summary, but never used as a fit objective (param_extraction/metrics.py ContrastEstimator).",
                    "vars"  : [
                        {"sym": r"C(a,r)",      "desc": "peak-to-floor contrast at pixel (a, r) in dB"},
                        {"sym": r"|T_h|",       "desc": "tomogram magnitude at elevation bin h"},
                        {"sym": r"\mathcal{F}", "desc": "set of the m lowest-amplitude elevation bins"},
                        {"sym": r"m",           "desc": "floor sample count"},
                        {"sym": r"f",           "desc": "floor_fraction = 0.25"},
                        {"sym": r"H",           "desc": "number of elevation bins"},
                    ],
                },
                {
                    "title" : "K-selection margin and ambiguity",
                    "tex"   : r"\Delta^{(2)}(a,r) = \min_{K \neq K^*} \mathrm{pen}_K - \mathrm{pen}_{K^*}, \qquad \rho = \frac{\Delta^{(2)}}{\max(|\mathrm{pen}_{K^*}|,\,10^{-12})}, \qquad \mathrm{amb} = \Pr[\rho < \tau]",
                    "note"  : "Per-pixel confidence of the best-K choice: the penalised-score gap from the winner to the second-best model order and its size relative to the winner; the ambiguous fraction is the share of pixels (with a valid second-best) whose relative margin falls below tau. Prev/next-neighbour margins are also emitted (param_extraction/metrics.py KSelectionDiagnostics).",
                    "vars"  : [
                        {"sym": r"\Delta^{(2)}",   "desc": "penalised-score gap to the second-best order"},
                        {"sym": r"\mathrm{pen}_K", "desc": "penalised score of model order K"},
                        {"sym": r"K^*",            "desc": "selected (winning) model order"},
                        {"sym": r"\rho",           "desc": "relative margin"},
                        {"sym": r"\tau",           "desc": "ambiguity_threshold = 0.05"},
                        {"sym": r"\mathrm{amb}",   "desc": "fraction of valid pixels with rho < tau"},
                    ],
                },
                {
                    "title" : "Activity map and count fractions",
                    "tex"   : r"n^{\mathrm{act}}(a,r) = \sum_{k=1}^{K_{\max}} \mathbf{1}\!\left[a_k \geq 10^{-3}\right], \qquad \mathrm{frac}_j = \frac{\left|\{(a,r) : n^{\mathrm{act}} = j\}\right|}{N}",
                    "note"  : "How many components each pixel activates, and the global distribution over counts 0 to K_max (also a fitted-only variant frac_k_fitted normalised by the count of pixels with n_act > 0).",
                    "vars"  : [
                        {"sym": r"n^{\mathrm{act}}(a,r)", "desc": "active component count at pixel (a, r)"},
                        {"sym": r"a_k",                   "desc": "fitted amplitude of slot k"},
                        {"sym": r"K_{\max}",              "desc": "k_max = 5"},
                        {"sym": r"\mathrm{frac}_j",       "desc": "fraction of pixels with exactly j active slots"},
                        {"sym": r"N",                     "desc": "total pixel count"},
                    ],
                },
                {
                    "title" : "Mu separation maps",
                    "tex"   : r"\Delta\mu_{k,k+1}(a,r) = \left|\mu_{k+1} - \mu_k\right| \quad \text{where } a_k \geq 10^{-3} \wedge a_{k+1} \geq 10^{-3}",
                    "note"  : "Spatial maps of the elevation gap between adjacent active components, NaN elsewhere; reveals layer-separation structure (only emitted when n_gaussians >= 2).",
                    "vars"  : [
                        {"sym": r"\Delta\mu_{k,k+1}", "desc": "elevation gap between slots k and k+1 (m)"},
                        {"sym": r"\mu_k, \mu_{k+1}",  "desc": "mean elevations of adjacent slots (m)"},
                        {"sym": r"a_k, a_{k+1}",      "desc": "amplitudes; both must be active"},
                    ],
                },
            ],
        }

    def _dataset(self) -> dict:
        """Returns the dataset group: splitting, patch tiling, complex representation, augmentation and normalisation."""
        return {
            "group" : "Dataset",
            "blurb" : "Reduced artifacts to PyTorch loaders: cropping, patch tiling, complex-to-real representation, augmentation, optional per-pixel geometry attachment, and fitted per-channel normalisation.",
            "items" : [
                {
                    "title" : "Split coordinate transform",
                    "tex"   : r"\mathrm{az_{slice}} = \left[\,\mathrm{az}^{S}_{\mathrm{start}} - \mathrm{az}^{G}_{\mathrm{start}},\ \ \mathrm{az}^{S}_{\mathrm{end}} - \mathrm{az}^{G}_{\mathrm{start}}\,\right), \qquad \mathrm{rg_{slice}} = \left[\,\mathrm{rg}^{S}_{\mathrm{start}} - \mathrm{rg}^{G}_{\mathrm{start}},\ \ \mathrm{rg}^{S}_{\mathrm{end}} - \mathrm{rg}^{G}_{\mathrm{start}}\,\right)",
                    "note"  : "Each train/val/test region is converted from absolute pixel coordinates to zero-based slices into the memory-mapped global crop.",
                    "vars"  : [
                        {"sym": r"\mathrm{az_{slice}}, \mathrm{rg_{slice}}", "desc": "zero-based array slices along azimuth and range"},
                        {"sym": r"\mathrm{az}^{S}, \mathrm{rg}^{S}",         "desc": "split region bounds (absolute pixels)"},
                        {"sym": r"\mathrm{az}^{G}, \mathrm{rg}^{G}",         "desc": "global crop bounds (absolute pixels)"},
                    ],
                },
                {
                    "title" : "Stacked complex input array",
                    "tex"   : r"\mathbf{X}[0] = \mathbf{s}_0, \qquad \mathbf{X}[1 : 1+N_s] = S, \qquad \mathbf{X}[1+N_s :] = I",
                    "note"  : "Primary, selected secondaries, and selected interferograms are written straight into one pre-allocated complex buffer of shape (1 + N_s + N_i, Az, Rg); the secondary and interferogram counts are independent.",
                    "vars"  : [
                        {"sym": r"\mathbf{X}",   "desc": "stacked complex input array"},
                        {"sym": r"\mathbf{s}_0", "desc": "primary SLC pass"},
                        {"sym": r"S",            "desc": "secondary SLC passes, shape (N_s, Az, Rg)"},
                        {"sym": r"I",            "desc": "interferogram passes, shape (N_i, Az, Rg)"},
                        {"sym": r"N_s, N_i",     "desc": "number of secondary and interferogram passes"},
                    ],
                },
                {
                    "title" : "Patch grid",
                    "tex"   : r"n_v = \left\lceil \frac{H - P_H}{s_v} \right\rceil + 1, \qquad n_h = \left\lceil \frac{W - P_W}{s_h} \right\rceil + 1, \qquad N_p = n_v \cdot n_h",
                    "note"  : "Sliding-window tiling of the split region; a dimension no larger than the patch yields a single row or column. Patches and strides are rectangular (azimuth, range) pairs, so the two axes tile independently.",
                    "vars"  : [
                        {"sym": r"n_v, n_h", "desc": "patch rows and columns"},
                        {"sym": r"H, W",     "desc": "spatial height and width of the split (pixels)"},
                        {"sym": r"P_H, P_W", "desc": "patch size (azimuth, range), default (64, 32)"},
                        {"sym": r"s_v, s_h", "desc": "stride (azimuth, range), default (32, 16)"},
                        {"sym": r"N_p",      "desc": "total patch count"},
                    ],
                },
                {
                    "title" : "Symmetric grid padding",
                    "tex"   : r"p_v = P_H + (n_v - 1)\,s_v - H, \qquad p_h = P_W + (n_h - 1)\,s_h - W",
                    "note"  : "The minimal padding that makes the grid tile the domain exactly; boundary patches use symmetric reflection by default.",
                    "vars"  : [
                        {"sym": r"p_v, p_h", "desc": "total vertical and horizontal padding (pixels)"},
                        {"sym": r"P_H, P_W", "desc": "patch height and width"},
                        {"sym": r"n_v, n_h", "desc": "patch rows and columns"},
                        {"sym": r"s_v, s_h", "desc": "vertical and horizontal stride"},
                        {"sym": r"H, W",     "desc": "spatial height and width"},
                    ],
                },
                {
                    "title" : "Padding split and patch corners",
                    "tex"   : r"p_{\mathrm{top}} = \left\lfloor p_v/2 \right\rfloor, \quad p_{\mathrm{bot}} = p_v - p_{\mathrm{top}}, \qquad v_0 = i_v\,s_v - p_{\mathrm{top}}, \quad h_0 = i_h\,s_h - p_{\mathrm{left}}",
                    "note"  : "Padding is split evenly per side; each patch corner may be negative, marking a padded region applied in a single np.pad call.",
                    "vars"  : [
                        {"sym": r"p_{\mathrm{top}}, p_{\mathrm{bot}}", "desc": "top and bottom padding (left/right analogous)"},
                        {"sym": r"p_v",                                "desc": "total vertical padding"},
                        {"sym": r"(v_0, h_0)",                         "desc": "patch top-left corner in the padded array"},
                        {"sym": r"(i_v, i_h)",                         "desc": "patch grid indices"},
                        {"sym": r"s_v, s_h",                           "desc": "vertical and horizontal stride"},
                    ],
                },
                {
                    "title" : "Complex-to-real representations",
                    "tex"   : r"|s| = \sqrt{s_r^2 + s_i^2}, \qquad \angle s = \arg(s) \in (-\pi, \pi], \qquad \frac{s_r}{|s|},\ \ \frac{s_i}{|s|}",
                    "note"  : "Six modes combine these channels (mag_only, angle_only, real_imag, mag_angle, mag_real_imag, mag_ri_angle); the default uses magnitude for SLCs and phase for interferograms. Zero magnitude is replaced by 1 for the normalised components.",
                    "vars"  : [
                        {"sym": r"s",        "desc": "complex SLC or interferogram value"},
                        {"sym": r"s_r, s_i", "desc": "real and imaginary parts"},
                        {"sym": r"|s|",      "desc": "magnitude"},
                        {"sym": r"\angle s", "desc": "phase (radians)"},
                    ],
                },
                {
                    "title" : "Per-pass channel interleaving",
                    "tex"   : r"\mathrm{out}[:,\,k\,] = \mathrm{ch}_{(k \bmod c)}\!\left[:,\,\lfloor k/c \rfloor\,\right], \qquad k = 0,\dots,Pc-1",
                    "note"  : "All c channels of a pass stay contiguous; channels of the same kind repeat with stride c, the convention assumed by the normalisation slot mapping.",
                    "vars"  : [
                        {"sym": r"\mathrm{out}",                   "desc": "channel-expanded real output array"},
                        {"sym": r"\mathrm{ch}_{c_{\mathrm{idx}}}", "desc": "decomposed channel array (e.g. magnitude)"},
                        {"sym": r"k",                              "desc": "output channel index"},
                        {"sym": r"c",                              "desc": "channels per pass for the selected mode (1 to 4)"},
                        {"sym": r"P",                              "desc": "number of passes in the source"},
                    ],
                },
                {
                    "title" : "Input tensor assembly",
                    "tex"   : r"\mathbf{x} = \left[\,\mathrm{rep}(s_0)\ \middle|\ \mathrm{rep}(S_1),\dots,\mathrm{rep}(S_{N_s})\ \middle|\ \mathrm{rep}(I_1),\dots,\mathrm{rep}(I_{N_i})\ \middle|\ \mathbf{d}\,\right]",
                    "note"  : "Per patch, each enabled source is converted by its representation and concatenated along the channel axis, with the optional DEM channel last.",
                    "vars"  : [
                        {"sym": r"\mathbf{x}",          "desc": "assembled input tensor, shape (C_in, P_H, P_W)"},
                        {"sym": r"\mathrm{rep}(\cdot)", "desc": "complex-to-real conversion"},
                        {"sym": r"s_0",                 "desc": "primary SLC patch"},
                        {"sym": r"S_i, I_i",            "desc": "secondary and interferogram patches"},
                        {"sym": r"N_s, N_i",            "desc": "number of secondary and interferogram passes"},
                        {"sym": r"\mathbf{d}",          "desc": "optional DEM elevation patch (1 channel)"},
                    ],
                },
                {
                    "title" : "Input channel count",
                    "tex"   : r"C_{\mathrm{in}} = c_{\mathrm{prim}} + N_s\,c_{\mathrm{sec}} + N_i\,c_{\mathrm{ifg}} + c_{\mathrm{dem}}",
                    "note"  : "Total input width follows from which sources are enabled and the representation chosen for each; secondaries and interferograms are counted independently.",
                    "vars"  : [
                        {"sym": r"C_{\mathrm{in}}",   "desc": "total input channel count"},
                        {"sym": r"c_{\mathrm{prim}}", "desc": "channels of the primary pass (0 if disabled)"},
                        {"sym": r"c_{\mathrm{sec}}",  "desc": "channels per secondary pass"},
                        {"sym": r"c_{\mathrm{ifg}}",  "desc": "channels per interferogram pass"},
                        {"sym": r"c_{\mathrm{dem}}",  "desc": "1 if use_dem else 0"},
                        {"sym": r"N_s, N_i",          "desc": "number of secondary and interferogram passes"},
                    ],
                },
                {
                    "title" : "Output tensor selection",
                    "tex"   : r"\mathbf{y} = \left[\theta_{c_1}, \theta_{c_2}, \dots, \theta_{c_{C_{\mathrm{out}}}}\right], \qquad C_{\mathrm{out}} = n_g \cdot p_g",
                    "note"  : "The configured subset of Gaussian parameters is selected from the interleaved ground-truth layout (per Gaussian: base index g*3 plus the role offset amp=0/mu=1/sig=2).",
                    "vars"  : [
                        {"sym": r"\mathbf{y}",       "desc": "output (GT parameter) tensor"},
                        {"sym": r"\theta_{c_i}",     "desc": "i-th selected parameter channel"},
                        {"sym": r"\{c_i\}",          "desc": "indices chosen from the interleaved layout"},
                        {"sym": r"C_{\mathrm{out}}", "desc": "selected output channel count"},
                        {"sym": r"n_g",              "desc": "n_gaussians, the k_max of the parameter extraction"},
                        {"sym": r"p_g",              "desc": "params per Gaussian, default 3 (amp, mu, sigma)"},
                    ],
                },
                {
                    "title" : "Flip augmentations",
                    "tex"   : r"\mathbf{x}'[\dots, i] = \mathbf{x}[\dots, P_W - 1 - i] \ \ (p_H = 0.5), \qquad \mathbf{x}'[\dots, j, :] = \mathbf{x}[\dots, P_H - 1 - j, :] \ \ (p_V = 0.5)",
                    "note"  : "Horizontal and vertical flips are drawn independently and applied jointly (pre-normalisation) to the input, the target, and (when a physics loss is active) the per-pixel geometry field, preserving spatial correspondence.",
                    "vars"  : [
                        {"sym": r"\mathbf{x}, \mathbf{x}'", "desc": "patch before and after the flip (target and geometry alike)"},
                        {"sym": r"i",                       "desc": "range (horizontal) axis index"},
                        {"sym": r"j",                       "desc": "azimuth (vertical) axis index"},
                        {"sym": r"P_H, P_W",                "desc": "patch height and width"},
                        {"sym": r"p_H, p_V",                "desc": "flip probabilities"},
                    ],
                },
                {
                    "title" : "Random 90° rotation",
                    "tex"   : r"(\mathbf{x}', \mathbf{y}') = \mathrm{rot90}^{\,k}(\mathbf{x}, \mathbf{y}), \qquad k \sim \mathcal{U}\{1, 2, 3\}",
                    "note"  : "Joint rotation in the spatial plane, disabled by default (p_rot90 = 0) and force-skipped whenever a per-pixel geometry field is active (a warning fires if p_rot90 > 0 in that case); rotation could mix unequal azimuth and range pixel spacings.",
                    "vars"  : [
                        {"sym": r"\mathbf{x}, \mathbf{y}", "desc": "input and GT parameter patches"},
                        {"sym": r"k",                      "desc": "number of 90° turns, uniform over {1, 2, 3}"},
                        {"sym": r"\mathcal{U}",            "desc": "uniform distribution"},
                    ],
                },
                {
                    "title" : "Additive Gaussian input noise",
                    "tex"   : r"\mathbf{x}' = \mathbf{x} + \varepsilon, \qquad \varepsilon \sim \mathcal{N}\!\left(0,\ \sigma_{\mathrm{noise}}^2\,\mathbf{I}\right) \ \ (p_N = 0,\ \text{off by default})",
                    "note"  : "Applied to the already-normalised input on the train split only (so the std is in normalised units) and disabled by default (p_noise = 0); the regression target and the geometry field are never perturbed.",
                    "vars"  : [
                        {"sym": r"\mathbf{x}, \mathbf{x}'", "desc": "input patch before and after"},
                        {"sym": r"\varepsilon",             "desc": "noise tensor, same shape as the input"},
                        {"sym": r"\sigma_{\mathrm{noise}}", "desc": "noise_std = 0.01"},
                        {"sym": r"\mathbf{I}",              "desc": "identity covariance (i.i.d. noise)"},
                        {"sym": r"p_N",                     "desc": "noise probability (p_noise, default 0)"},
                    ],
                },
                {
                    "title" : "Per-pixel geometry field (kz)",
                    "tex"   : r"b_\perp = b_h\cos\theta + b_v\sin\theta, \qquad k_z = \frac{4\pi}{\lambda}\,\frac{b_\perp}{r\,\sin\theta}\ \ (\text{height}), \qquad k_z = \frac{4\pi}{\lambda}\,\frac{b_\perp}{r}\ \ (\text{slant})",
                    "note"  : "When a physics loss needs per-pixel vertical wavenumbers, the preprocessing geometry_field.npz is loaded, subset to the selected secondaries, and validated against the global crop. Each split region slices its own kz(az, rg, track) map, which rides through the loader as an unnormalised third tensor, is flip-augmented jointly with the input and target, and skips 90° rotation. Built only when build_geometry_field is set (driven by TrainingPipeline.physics_geometry_active: any active curriculum stage with use_coherence_resyn / use_covariance_match / use_capon_cycle); the height convention scales the denominator by sin(theta), the slant convention does not.",
                    "vars"  : [
                        {"sym": r"k_z",      "desc": "per-pixel vertical wavenumber, one map per track"},
                        {"sym": r"b_\perp",  "desc": "perpendicular baseline"},
                        {"sym": r"b_h, b_v", "desc": "horizontal and vertical baseline components"},
                        {"sym": r"\theta",   "desc": "look angle (per range sample)"},
                        {"sym": r"r",        "desc": "slant range (per range sample)"},
                        {"sym": r"\lambda",  "desc": "radar wavelength"},
                    ],
                },
                {
                    "title" : "Stats fit — robust IQR with log1p",
                    "tex"   : r"f(x) = \log\!\big(1 + \max(x, 0)\big), \qquad \mu_c = P_{50}\big(f(x)\big), \qquad s_c = P_{75}\big(f(x)\big) - P_{25}\big(f(x)\big)",
                    "note"  : "The ROBUST_IQR_LOG1P strategy: median and interquartile range of the log-compressed values. The live slot mapping assigns it to the heavy-tailed channels — the SLC and interferogram magnitude slots and the output amplitude and sigma pools; the scale is floored at 1e-8 (configuration/normalization/general.py).",
                    "vars"  : [
                        {"sym": r"\mu_c", "desc": "fitted location of channel group c"},
                        {"sym": r"s_c",   "desc": "fitted scale of channel group c"},
                        {"sym": r"P_q",   "desc": "q-th percentile of the collected values"},
                        {"sym": r"f",     "desc": "log1p compression applied before fitting"},
                        {"sym": r"x",     "desc": "collected sample values of the group"},
                    ],
                },
                {
                    "title" : "Stats fit — z-score",
                    "tex"   : r"\mu_c = \mathrm{mean}(x), \qquad s_c = \max\!\big(\mathrm{std}(x),\ 10^{-8}\big)",
                    "note"  : "The ZSCORE strategy: mean and standard deviation with no compression. The live slot mapping assigns it to the well-behaved channels — the raw and magnitude-normalised re/im components, the SLC (pass) phase slot, the output mu pool, and the DEM elevation channel. Interferogram phase instead uses the fixed pi scaling below; MIN_MAX_P999 remains defined but is not referenced by the current slot mapping (configuration/normalization/general.py).",
                    "vars"  : [
                        {"sym": r"\mu_c, s_c", "desc": "fitted location and scale of the group"},
                        {"sym": r"x",          "desc": "collected sample values of the group"},
                    ],
                },
                {
                    "title" : "Stats fit — fixed pi scaling",
                    "tex"   : r"\mu_c = 0, \qquad s_c = \pi, \qquad \hat{x}_c = \frac{x_c}{\pi}",
                    "note"  : "The FIXED_DIV_PI strategy: a constant location 0 and scale pi, so no samples are collected or fitted for the channel (its group is excluded from the collector via the needs_data filter). The live slot mapping assigns it to interferogram phase, mapping the (-pi, pi] phase onto roughly (-1, 1] (configuration/normalization/general.py).",
                    "vars"  : [
                        {"sym": r"\mu_c, s_c", "desc": "fixed location (0) and scale (pi) of the group"},
                        {"sym": r"x_c",        "desc": "physical-space value (interferogram phase, radians)"},
                        {"sym": r"\hat{x}_c",  "desc": "normalised value of channel c"},
                    ],
                },
                {
                    "title" : "Forward normalisation",
                    "tex"   : r"\hat{x}_c = \frac{f(x_c) - \mu_c}{s_c}, \qquad f(x_c) = \log\!\big(1 + x_c\big)\ \text{if log1p, else}\ x_c",
                    "note"  : "Statistics are fitted on the training split only and applied identically to all splits; log1p inputs are floored at 0 (when re-normalising predictions inside the loss the floor is leaky with clamp_leaky_slope, so amplitude gradients survive below it), and the output amplitude, mu and sigma pools exclude inactive slots (amplitude below 1e-3, stats_computer.py).",
                    "vars"  : [
                        {"sym": r"\hat{x}_c",  "desc": "normalised value of channel c"},
                        {"sym": r"x_c",        "desc": "physical-space value of channel c"},
                        {"sym": r"f",          "desc": "optional log1p compression"},
                        {"sym": r"\mu_c, s_c", "desc": "fitted location and scale of channel c"},
                    ],
                },
                {
                    "title" : "Inverse normalisation",
                    "tex"   : r"x_c = \exp\!\big(\hat{x}_c\,s_c + \mu_c\big) - 1\ \ \text{(log1p)}, \qquad x_c = \hat{x}_c\,s_c + \mu_c\ \ \text{(otherwise)}",
                    "note"  : "Used to recover physical units during loss computation and inference; the recovered value is clamped to the configured physical bounds (default [0, 200]). For log1p channels the clamp acts as [log1p(floor), log1p(ceil)] on the exponent argument (transforms.py Log1pTransform); channels normalised without log1p but flagged clampable in normalization_stats.json (amplitude and sigma, never mu) pass through the same leaky log-space barrier via compress then decompress, so out-of-range excursions are compressed logarithmically instead of escaping the bound. Each channel group is transformed by indexed selection (normalizer.py), never by evaluating both branches of a where.",
                    "vars"  : [
                        {"sym": r"x_c",        "desc": "recovered physical-space value"},
                        {"sym": r"\hat{x}_c",  "desc": "normalised value of channel c"},
                        {"sym": r"\mu_c, s_c", "desc": "fitted location and scale of channel c"},
                    ],
                },
            ],
        }

    def _training_loss(self) -> dict:
        """Returns the training-loss group: the switchable curve, physics and parameter loss terms with matching and clamping."""
        return {
            "group" : "Training · Loss",
            "blurb" : "The composable multi-term objective, term by term: fifteen switchable components over curve, physics, and parameter space, plus clamping, optimal-assignment matching, slot-presence weighting, and weight calibration.",
            "items" : [
                {
                    "title" : "Physical parameter bounds",
                    "tex"   : r"a \in \left[0,\ a_{\max}\right], \qquad \mu \in \left[x_{\min},\ x_{\max}\right], \qquad \sigma \in \left[\tfrac{\Delta x}{2},\ \tfrac{x_{\max} - x_{\min}}{2}\right]",
                    "note"  : "Denormalised predictions are clamped to these bounds before curve reconstruction, using a leaky clamp (normalization.param_clamp_leaky_slope, default 0.1, persisted in normalization_stats.json as param_leaky_slope) so gradients survive saturation, then renormalised (gaussians.py GaussianClamp, loss.py _prepare). Three leaky floors stack at amplitude 0 (decompress and compress leak with clamp_leaky_slope, the bounds clamp with param_clamp_leaky_slope), so the below-floor recovery gradient scales as clamp_leaky_slope squared times param_clamp_leaky_slope; the two knobs keep that composition controllable.",
                    "vars"  : [
                        {"sym": r"a",                  "desc": "predicted amplitude"},
                        {"sym": r"a_{\max}",           "desc": "normalization.amp_max, default 200"},
                        {"sym": r"\mu",                "desc": "predicted mean elevation"},
                        {"sym": r"\sigma",             "desc": "predicted spread"},
                        {"sym": r"\Delta x",           "desc": "elevation axis step (m)"},
                        {"sym": r"x_{\min}, x_{\max}", "desc": "elevation axis bounds (m)"},
                    ],
                },
                {
                    "title" : "Curve reconstruction",
                    "tex"   : r"\hat{y}(x_n) = \sum_{k=1}^{K} a_k\,\exp\!\left(-\frac{(x_n - \mu_k)^2}{2\sigma_k^2}\right), \qquad e_{b,n,h,w} = \hat{y}_{b,n,h,w} - y_{b,n,h,w}",
                    "note"  : "Predicted and GT parameters are evaluated on the elevation axis (GT under no_grad); the exponent is clamped to a numerical floor/ceil and sigma to a floor in code. The shared residual e feeds the four elementwise curve terms (mse, l1, huber, charbonnier); cosine reads the raw curves.",
                    "vars"  : [
                        {"sym": r"\hat{y}(x_n)",         "desc": "reconstructed curve value at sample x_n"},
                        {"sym": r"x_n",                  "desc": "elevation axis sample n of N"},
                        {"sym": r"K",                    "desc": "components, K = C / params_per_gaussian"},
                        {"sym": r"a_k, \mu_k, \sigma_k", "desc": "clamped predicted parameters of slot k"},
                        {"sym": r"e_{b,n,h,w}",          "desc": "residual at batch b, bin n, pixel (h, w)"},
                        {"sym": r"y_{b,n,h,w}",          "desc": "GT (experimental) curve value"},
                    ],
                },
                {
                    "title" : "Curve MSE",
                    "tex"   : r"\ell_{\mathrm{MSE}} = \frac{1}{BNHW}\sum_{b,n,h,w} e_{b,n,h,w}^2",
                    "note"  : "Mean squared error between reconstructed and experimental spectra over the full batch.",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{MSE}}", "desc": "MSE term value"},
                        {"sym": r"e_{b,n,h,w}",         "desc": "curve residual"},
                        {"sym": r"B, N, H, W",          "desc": "batch, elevation bins, patch height, patch width"},
                    ],
                },
                {
                    "title" : "Curve L1",
                    "tex"   : r"\ell_{L1} = \frac{1}{BNHW}\sum_{b,n,h,w} \left|e_{b,n,h,w}\right|",
                    "note"  : "Mean absolute error counterpart, less sensitive to large residuals.",
                    "vars"  : [
                        {"sym": r"\ell_{L1}",   "desc": "L1 term value"},
                        {"sym": r"e_{b,n,h,w}", "desc": "curve residual"},
                        {"sym": r"B, N, H, W",  "desc": "batch, elevation bins, patch height, patch width"},
                    ],
                },
                {
                    "title" : "Curve Huber",
                    "tex"   : r"\ell_{\mathrm{Huber}} = \frac{1}{BNHW}\sum_{b,n,h,w} \begin{cases} \frac{1}{2}e^2 & |e| \leq \delta \\ \delta\!\left(|e| - \frac{\delta}{2}\right) & \text{otherwise} \end{cases}",
                    "note"  : "Quadratic near zero, linear in the tails.",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{Huber}}", "desc": "Huber term value"},
                        {"sym": r"e",                     "desc": "curve residual at (b, n, h, w)"},
                        {"sym": r"\delta",                "desc": "huber_delta = 1.0"},
                        {"sym": r"B, N, H, W",            "desc": "batch, elevation bins, patch height, patch width"},
                    ],
                },
                {
                    "title" : "Curve Charbonnier",
                    "tex"   : r"\ell_{\mathrm{Charb}} = \frac{1}{BNHW}\sum_{b,n,h,w} \sqrt{e_{b,n,h,w}^2 + \varepsilon^2}",
                    "note"  : "A smooth differentiable approximation of L1; an inner clamp keeps the square root away from zero in code.",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{Charb}}", "desc": "Charbonnier term value"},
                        {"sym": r"e_{b,n,h,w}",           "desc": "curve residual"},
                        {"sym": r"\varepsilon",           "desc": "charbonnier_eps = 1e-3"},
                        {"sym": r"B, N, H, W",            "desc": "batch, elevation bins, patch height, patch width"},
                    ],
                },
                {
                    "title" : "Cosine distance",
                    "tex"   : r"\ell_{\cos} = \operatorname{mean}_{(b,h,w) \in V}\left(1 - \frac{\hat{y} \cdot y}{\|\hat{y}\|\,\|y\|}\right), \qquad V = \left\{(b,h,w) : \|y\| > 10^{-3}\right\}",
                    "note"  : "Shape agreement of the elevation-axis vectors, averaged only over pixels with non-negligible ground truth. In code both norms are floored at 1e-3 and the similarity clipped to [-1, 1].",
                    "vars"  : [
                        {"sym": r"\ell_{\cos}", "desc": "cosine distance term value"},
                        {"sym": r"\hat{y}, y",  "desc": "predicted and GT elevation-axis vectors per pixel"},
                        {"sym": r"\|\cdot\|",   "desc": "L2 norm along the elevation axis"},
                        {"sym": r"V",           "desc": "set of valid pixels"},
                    ],
                },
                {
                    "title" : "Tomographic forward operator (physics terms)",
                    "tex"   : r"k_z^{(i)} = \frac{4\pi\,b_i}{\lambda\,r_0\,\sin\theta_{\ell}}\ \ (\text{height}), \quad k_z^{(i)} = \frac{4\pi\,b_i}{\lambda\,r_0}\ \ (\text{slant}), \qquad A_{i,n} = \exp\!\left(j\,k_z^{(i)}\,\xi_n\right), \qquad O_{i,j,n} = A_{i,n}\,\overline{A_{j,n}}",
                    "note"  : "The vertical wavenumbers come from the configured geometry: baselines give k_z = 4*pi*b/(lambda*r0) under the 'slant' convention and additionally divide by sin(look) under the default 'height' convention, or explicit kz_values override them, or a per-pixel kz map (GeometryField) replaces the single geometry with per-track wavenumbers. Only three of the five physics terms - coherence re-synthesis, covariance matching, Capon cycle - use the steering matrix A and outer product O; total-power and moments operate on the curves directly. All physics terms reduce only over pixels whose GT integrated power exceeds the physics floor (1e-3) and all default off (tomo_geometry.py TomoGeometry, physical_loss.py).",
                    "vars"  : [
                        {"sym": r"k_z^{(i)}",     "desc": "vertical wavenumber of track i (rad/m)"},
                        {"sym": r"b_i",           "desc": "perpendicular baseline of track i (m)"},
                        {"sym": r"\lambda, r_0",  "desc": "wavelength and slant range (m)"},
                        {"sym": r"\theta_{\ell}", "desc": "look angle (default 45 deg, height convention only)"},
                        {"sym": r"A_{i,n}",       "desc": "steering matrix, track i at elevation bin n"},
                        {"sym": r"O_{i,j,n}",     "desc": "per-bin steering outer product"},
                        {"sym": r"\xi_n",         "desc": "elevation axis sample (m)"},
                    ],
                },
                {
                    "title" : "Total-power relative error",
                    "tex"   : r"p_0 = \sum_n \hat{y}_n\,\Delta\xi, \quad t_0 = \sum_n y_n\,\Delta\xi, \qquad \ell_{\mathrm{pow}} = \left\langle \frac{|p_0 - t_0|}{t_0} \right\rangle_{t_0 > \tau}",
                    "note"  : "Relative integrated-power error of the predicted spectrum, averaged over GT-strong pixels. Kept as a loss option though radiometric power is biased by Capon (physical_loss.py total_power).",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{pow}}", "desc": "total-power relative-error term"},
                        {"sym": r"p_0, t_0",            "desc": "integrated power of predicted and GT curves"},
                        {"sym": r"\Delta\xi",           "desc": "elevation bin spacing (m)"},
                        {"sym": r"\tau",                "desc": "physics_floor = 1e-3"},
                    ],
                },
                {
                    "title" : "Profile moments",
                    "tex"   : r"\bar{z} = \frac{\sum_n P_n\,\xi_n}{\sum_n P_n}, \quad \sigma_z = \sqrt{\frac{\sum_n P_n\,\xi_n^2}{\sum_n P_n} - \bar{z}^2 + 10^{-8}}, \qquad \ell_{\mathrm{mom}} = \left\langle \frac{w_0\frac{|\Delta m_0|}{t_0} + w_1\frac{|\Delta\bar{z}|}{\Delta\xi_R} + w_2\frac{|\Delta\sigma_z|}{\Delta\xi_R}}{w_0+w_1+w_2} \right\rangle",
                    "note"  : "Relative error of the first three profile moments - mass m0, centroid z-bar, and spread sigma_z - used as a validation-grade physics term; moment weights default (1, 1, 1) (physical_loss.py moments).",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{mom}}",                       "desc": "moments term value"},
                        {"sym": r"P_n",                                       "desc": "curve value at elevation bin n (pred or GT)"},
                        {"sym": r"\bar{z}, \sigma_z",                         "desc": "profile centroid and spread (m)"},
                        {"sym": r"\Delta m_0, \Delta\bar{z}, \Delta\sigma_z", "desc": "pred-minus-GT moment differences"},
                        {"sym": r"\Delta\xi_R",                               "desc": "elevation axis span x_max - x_min (m)"},
                        {"sym": r"w_0, w_1, w_2",                             "desc": "moments_weights, default (1, 1, 1)"},
                    ],
                },
                {
                    "title" : "Coherence re-synthesis",
                    "tex"   : r"\gamma_P\!\left(k_z^{(i)}\right) = \frac{\sum_n P_n\,e^{j\,k_z^{(i)}\xi_n}\,\Delta\xi}{\sum_n P_n\,\Delta\xi}, \qquad \ell_{\mathrm{coh\text{-}r}} = \left\langle \frac{1}{N_s}\sum_i \left|\gamma_P^{(i)} - \gamma_T^{(i)}\right|^2 \right\rangle",
                    "note"  : "Compares the mass-normalised characteristic functions (interferometric coherences) of the two profiles sampled at each track wavenumber; insensitive to absolute power, the top-ranked physics loss (physical_loss.py coherence_resynthesis).",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{coh\text{-}r}}", "desc": "coherence re-synthesis term value"},
                        {"sym": r"\gamma_P, \gamma_T",           "desc": "normalised coherences of predicted and GT profiles"},
                        {"sym": r"k_z^{(i)}",                    "desc": "vertical wavenumber of track i"},
                        {"sym": r"N_s",                          "desc": "number of tracks"},
                    ],
                },
                {
                    "title" : "Covariance matching",
                    "tex"   : r"\mathbf{R}[P] = \mathbf{A}\,\mathrm{diag}(P)\,\mathbf{A}^{H}\,\Delta\xi, \qquad \ell_{\mathrm{cov}} = \left\langle \frac{\left\|\mathbf{R}[P] - \mathbf{R}[T]\right\|_F^2}{\left\|\mathbf{R}[T]\right\|_F^2} \right\rangle",
                    "note"  : "Relative Frobenius error of the synthesised covariance; the linearity of R in P lets the implementation transform only the prediction-minus-GT difference. Insensitive to absolute scale (physical_loss.py covariance_matching).",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{cov}}",          "desc": "covariance matching term value"},
                        {"sym": r"\mathbf{R}[P], \mathbf{R}[T]", "desc": "covariances synthesised from predicted and GT profiles"},
                        {"sym": r"\mathbf{A}",                   "desc": "steering matrix exp(j kz xi)"},
                        {"sym": r"\|\cdot\|_F",                  "desc": "Frobenius norm over the track-pair axes"},
                    ],
                },
                {
                    "title" : "Capon cycle-consistency",
                    "tex"   : r"\hat{T}_P(\xi_n) = \frac{1}{\mathbf{a}^{H}(\xi_n)\big(\mathbf{R}[P] + \epsilon\,\bar{\sigma}\,\mathbf{I}\big)^{-1}\mathbf{a}(\xi_n)}, \quad \bar{\sigma} = \frac{\mathrm{tr}\,\mathbf{R}[P]}{N_s}, \qquad \ell_{\mathrm{cyc}} = \left\langle \frac{1}{N}\sum_n \left(\frac{\hat{T}_P(\xi_n)}{m_0^{\hat{T}}} - \frac{T(\xi_n)}{m_0^{T}}\right)^2 \right\rangle",
                    "note"  : "The most expensive physics term: synthesise the covariance from the prediction, apply signal-adaptive diagonal loading (loading*max(sigma-bar, floor)), Hermitianise, form the Capon spectrum by one solve per pixel, and compare mass-normalised spectra (physical_loss.py capon_cycle).",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{cyc}}",    "desc": "Capon cycle-consistency term value"},
                        {"sym": r"\hat{T}_P(\xi_n)",       "desc": "Capon spectrum re-synthesised from the prediction"},
                        {"sym": r"\bar{\sigma}",           "desc": "mean diagonal power for adaptive loading"},
                        {"sym": r"\epsilon",               "desc": "capon_loading = 1e-2"},
                        {"sym": r"m_0^{\hat{T}}, m_0^{T}", "desc": "integrated power normalisers"},
                        {"sym": r"N, N_s",                 "desc": "elevation bins and number of tracks"},
                    ],
                },
                {
                    "title" : "GT sort and optimal prediction matching",
                    "tex"   : r"\pi^\star_{h,w} = \operatorname*{argmin}_{\pi \in S_K} \sum_k \mathbf{1}\!\left[a^{\mathrm{GT}}_k > \tau_a\right] \sum_p \left|\hat{\theta}_{\pi(k),p} - \theta^{\mathrm{GT}}_{k,p}\right|, \qquad \hat{\Theta} \leftarrow \hat{\Theta}_{\pi^\star}",
                    "note"  : "Both modes first sort GT components by mu with inactive GT slots (amp <= tau_a = amp_zero_thr = 1e-4) pushed last. Under param_matching = 'hungarian' - the shipped full-model and curriculum default (AblationCatalog.PARAM_MATCH_FULL) as well as the bare LossConfig default - predictions are permuted to the GT slots per pixel by the optimal assignment minimising the active-weighted L1 cost, found by exhaustive enumeration of all K! permutations (param_loss.py ParamMatcher, K <= MAX_GAUSSIANS = 6), making the loss permutation-invariant in the predicted slot order. Under param_matching = 'sorted_gt' predictions keep their slot order (positional matching), so each predicted slot learns a fixed rank along the height axis.",
                    "vars"  : [
                        {"sym": r"\pi^\star_{h,w}",                    "desc": "optimal pred-to-GT slot permutation at pixel (h, w)"},
                        {"sym": r"S_K",                                "desc": "all K! slot permutations"},
                        {"sym": r"a^{\mathrm{GT}}_k",                  "desc": "GT amplitude of slot k at physical scale"},
                        {"sym": r"\tau_a",                             "desc": "active-slot threshold, amp_zero_thr = 1e-4"},
                        {"sym": r"\hat{\theta}, \theta^{\mathrm{GT}}", "desc": "predicted and GT slot parameters"},
                        {"sym": r"\hat{\Theta}_{\pi^\star}",           "desc": "predictions reordered by the optimal permutation"},
                    ],
                },
                {
                    "title" : "Parameter activity mask and element weights",
                    "tex"   : r"m_{b,k,p} = \begin{cases} 1 & p = a \\ \mathbf{1}\!\left[a^{\mathrm{GT}}_{b,k} > \tau_a\right] & p \in \{\mu, \sigma\} \end{cases}, \qquad W_{b,k,p} = w_p\,m_{b,k,p}\,\rho_{b,k}\,(\phi_{b,k}\ \text{if } p=a)",
                    "note"  : "The per-element weight multiplies the per-parameter weight by the activity mask, the slot-presence scale, and (for amplitude) the focal scale. The amplitude channel is always supervised; mu and sigma receive zero weight on inactive GT slots. param_weights must supply exactly params_per_gaussian entries or the term raises a ValueError (loss.py _param_term).",
                    "vars"  : [
                        {"sym": r"m_{b,k,p}",             "desc": "activity mask for sample b, slot k, parameter p"},
                        {"sym": r"p",                     "desc": "parameter role: a, mu, or sigma"},
                        {"sym": r"a^{\mathrm{GT}}_{b,k}", "desc": "GT amplitude at physical scale"},
                        {"sym": r"\tau_a",                "desc": "amp_zero_thr = 1e-4"},
                        {"sym": r"w_p",                   "desc": "param_weights, default (1, 1, 1)"},
                        {"sym": r"\rho_{b,k}",            "desc": "slot-presence scale (see below)"},
                        {"sym": r"\phi_{b,k}",            "desc": "amplitude focal scale (see below)"},
                    ],
                },
                {
                    "title" : "Slot-presence scaling and focal amplitude weight",
                    "tex"   : r"\rho_{b,k} = a^{\mathrm{act}}_{b,k}\,w_{\mathrm{act},k} + (1-a^{\mathrm{act}}_{b,k})\,w_{\mathrm{inact},k}, \qquad w_{\mathrm{act},k} = \frac{1}{2 f_k}, \quad w_{\mathrm{inact},k} = \frac{1}{2(1-f_k)}, \qquad \phi_{b,k} = \left(\frac{|\hat a_{b,k} - a^{\mathrm{GT}}_{b,k}|}{|\hat a_{b,k} - a^{\mathrm{GT}}_{b,k}| + \delta_\phi}\right)^{\!\gamma}",
                    "note"  : "Optional reweighting to counter slot collapse under imbalanced occupancy. With presence_balance each slot k is balanced by its own batch active fraction f_k, equalising the total active and inactive weight mass within every slot; f_k is clamped to [1e-3, 1 - 1e-3] (FRAC_CLAMP) so degenerate all-active or all-empty batch slots cannot blow up the weights. Without presence_balance the global active_weight/inactive_weight apply to every slot. The focal weight (gamma > 0) up-weights amplitude slots the model gets wrong on a detached amplitude difference; gamma = 0 disables it (returns 1). All default off (param_loss.py presence_scale, focal_scale).",
                    "vars"  : [
                        {"sym": r"\rho_{b,k}",                               "desc": "slot-presence weight of slot k"},
                        {"sym": r"a^{\mathrm{act}}_{b,k}",                   "desc": "1 if GT slot active (a > tau_a), else 0"},
                        {"sym": r"w_{\mathrm{act},k}, w_{\mathrm{inact},k}", "desc": "per-slot balanced weights; without presence_balance the global active_weight, inactive_weight (default 1, 1)"},
                        {"sym": r"f_k",                                      "desc": "batch active fraction of slot k, clamped to [1e-3, 1 - 1e-3]"},
                        {"sym": r"\phi_{b,k}",                               "desc": "amplitude focal scale"},
                        {"sym": r"\gamma",                                   "desc": "amp_focal_gamma (default 0, off)"},
                        {"sym": r"\delta_\phi",                              "desc": "amp_focal_delta = 0.5"},
                    ],
                },
                {
                    "title" : "Active-set reduction",
                    "tex"   : r"\ell = \frac{\sum_{b,k,p,h,w} W \cdot \ell^{\mathrm{elem}}}{\sum_{b,k,p,h,w} W}\quad(\text{active norm}), \qquad \ell = \operatorname{mean}\!\left(W \cdot \ell^{\mathrm{elem}}\right)\quad(\text{default})",
                    "note"  : "With use_active_normalization the weighted parameter terms divide by the summed weights (clamped at 1e-6, the effective active count) instead of the plain element mean, so empty slots do not dilute the per-slot error. Default off in bare LossConfig but on in the shipped curriculum (param_loss.py _reduce).",
                    "vars"  : [
                        {"sym": r"W",                    "desc": "per-element weight (mask x param weight x presence x focal)"},
                        {"sym": r"\ell^{\mathrm{elem}}", "desc": "per-element loss contribution (abs, Huber, or squared)"},
                    ],
                },
                {
                    "title" : "Weighted parameter L1",
                    "tex"   : r"\ell_{\mathrm{param\text{-}L1}} = \operatorname{reduce}_{b,k,p,h,w}\!\left(w_p\,m_{b,k,p,h,w}\,\left|\hat{\theta}_{b,k,p,h,w} - \theta_{b,k,p,h,w}\right|\right)",
                    "note"  : "Direct parameter-space supervision over the matched effective slots K = min(K_pred, K_GT); the reduction is the active-set reduction above (mean, or weight-normalised sum). Per-parameter contributions are additionally logged as param_l1/amp, param_l1/mu, param_l1/sigma.",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{param\text{-}L1}}", "desc": "parameter L1 term value"},
                        {"sym": r"\hat{\theta}, \theta",            "desc": "predicted and GT parameters (normalised space)"},
                        {"sym": r"w_p",                             "desc": "per-parameter weight (a, mu, sigma)"},
                        {"sym": r"m",                               "desc": "activity mask"},
                        {"sym": r"b, k, p, h, w",                   "desc": "batch, slot, parameter, pixel indices"},
                    ],
                },
                {
                    "title" : "Weighted parameter Huber",
                    "tex"   : r"\ell_{\mathrm{param\text{-}Huber}} = \operatorname{reduce}\!\left(w_p\,m \cdot \begin{cases} \frac{1}{2}(\hat{\theta}-\theta)^2 & |\hat{\theta}-\theta| \leq \delta_p \\ \delta_p\!\left(|\hat{\theta}-\theta| - \frac{\delta_p}{2}\right) & \text{otherwise} \end{cases}\right)",
                    "note"  : "Huber counterpart of the parameter loss, robust to slot outliers; same active-set reduction as the L1 variant.",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{param\text{-}Huber}}", "desc": "parameter Huber term value"},
                        {"sym": r"\hat{\theta}, \theta",               "desc": "predicted and GT parameters (normalised space)"},
                        {"sym": r"\delta_p",                           "desc": "param_huber_delta = 0.5"},
                        {"sym": r"w_p",                                "desc": "per-parameter weight"},
                        {"sym": r"m",                                  "desc": "activity mask"},
                    ],
                },
                {
                    "title" : "Weighted parameter MSE",
                    "tex"   : r"\ell_{\mathrm{param\text{-}MSE}} = \operatorname{reduce}_{b,k,p,h,w}\!\left(w_p\,m_{b,k,p,h,w}\,\left(\hat{\theta}_{b,k,p,h,w} - \theta_{b,k,p,h,w}\right)^2\right)",
                    "note"  : "Quadratic counterpart of the parameter loss over the matched effective slots K = min(K_pred, K_GT); penalises large slot errors more strongly than the L1 and Huber variants; same active-set reduction.",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{param\text{-}MSE}}", "desc": "parameter MSE term value"},
                        {"sym": r"\hat{\theta}, \theta",             "desc": "predicted and GT parameters (normalised space)"},
                        {"sym": r"w_p",                              "desc": "per-parameter weight (a, mu, sigma)"},
                        {"sym": r"m",                                "desc": "activity mask"},
                        {"sym": r"b, k, p, h, w",                    "desc": "batch, slot, parameter, pixel indices"},
                    ],
                },
                {
                    "title" : "Legacy parameter MSE",
                    "tex"   : r"\tilde{\theta}_{k,p} = \frac{\theta_{k,p} - l_{k,p}}{u_{k,p} - l_{k,p}}, \qquad \ell_{\mathrm{param\text{-}legacy}} = \operatorname{mean}_{b,k,p,h,w}\left(\hat{\tilde{\theta}} - \tilde{\theta}\right)^2",
                    "note"  : "Imitation of the pre-Hungarian objective: both prediction and GT are min-max scaled by fixed per-slot physical bounds, then compared with a plain unweighted, unmasked MSE over every slot and parameter. It requires param_matching = sorted_gt (the bounds assume fixed slot identity, Loss._validate_legacy raises otherwise) and exactly two Gaussian slots, and the bound tuples must carry six entries ordered amp1, mu1, sigma1, amp2, mu2, sigma2 with max > min (param_loss.py LegacyParamLoss). The loss-scale probe forces this term off unless it is explicitly enabled.",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{param\text{-}legacy}}", "desc": "legacy parameter term value"},
                        {"sym": r"\theta_{k,p}, \hat{\theta}_{k,p}",    "desc": "GT and predicted parameter p of slot k, physical scale"},
                        {"sym": r"l_{k,p}, u_{k,p}",                    "desc": "legacy_bounds_min and legacy_bounds_max, six entries each"},
                        {"sym": r"\tilde{\theta}",                      "desc": "parameter mapped into the legacy min-max space"},
                        {"sym": r"k",                                   "desc": "slot index, exactly two slots"},
                    ],
                },
                {
                    "title" : "Smoothness (total variation)",
                    "tex"   : r"\ell_{\mathrm{TV}} = \operatorname{mean}_{b,c,h,w}\left|\hat{\theta}_{b,c,h+1,w} - \hat{\theta}_{b,c,h,w}\right| + \operatorname{mean}_{b,c,h,w}\left|\hat{\theta}_{b,c,h,w+1} - \hat{\theta}_{b,c,h,w}\right|",
                    "note"  : "Anisotropic TV in normalised parameter space; the two directional means are computed over their own difference tensors and summed.",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{TV}}",     "desc": "smoothness term value"},
                        {"sym": r"\hat{\theta}_{b,c,h,w}", "desc": "normalised predicted parameter at channel c, pixel (h, w)"},
                        {"sym": r"b, c, h, w",             "desc": "batch, parameter channel, pixel indices"},
                    ],
                },
                {
                    "title" : "Normalised weighted total loss",
                    "tex"   : r"\mathcal{L}_{\mathrm{total}} = \frac{\sum_j \alpha_j\,\ell_j}{\sum_j \alpha_j}",
                    "note"  : "Sum over enabled terms divided by the total of their weights; when no term is enabled the accumulated loss stays zero and the weight-normalisation division is skipped. Each term's weight is its user-selected weight_* value directly - the user is responsible for scaling terms to comparable magnitude. A curriculum may swap the whole configuration at a fixed epoch.",
                    "vars"  : [
                        {"sym": r"\mathcal{L}_{\mathrm{total}}", "desc": "scalar training loss"},
                        {"sym": r"\ell_j",                       "desc": "raw value of enabled term j"},
                        {"sym": r"\alpha_j",                     "desc": "user weight, the weight_* config value of term j"},
                        {"sym": r"j",                            "desc": "index over enabled terms (use_* = True)"},
                    ],
                },
                {
                    "title" : "Loss scale probe - outlier filter",
                    "tex"   : r"\mathrm{keep}\ v \iff Q_1 - 3\,\mathrm{IQR} \leq v \leq Q_3 + 3\,\mathrm{IQR}, \qquad \mathrm{IQR} = Q_3 - Q_1",
                    "note"  : "The probe forces every term's use flag on (unless overridden via enabled_losses) with weight 1 over a few batches; per-term raw values pass an IQR filter before averaging, reverting to the raw list if fewer than 3 survive (loss_probe.py).",
                    "vars"  : [
                        {"sym": r"v",            "desc": "raw per-batch value of one term"},
                        {"sym": r"Q_1, Q_3",     "desc": "first and third quartiles of the values"},
                        {"sym": r"\mathrm{IQR}", "desc": "interquartile range"},
                        {"sym": r"3",            "desc": "filter width factor k"},
                    ],
                },
                {
                    "title" : "Loss scale probe - suggested scale factor",
                    "tex"   : r"\nu_i = \frac{1}{\overline{\ell_i}} \qquad \text{or} \qquad \nu_i = \frac{\overline{\ell_{\mathrm{ref}}}}{\overline{\ell_i}}",
                    "note"  : "Diagnostic only: a scale factor to fold into weight_i so terms reach a comparable magnitude - each term scaled to unit magnitude, or to the magnitude of a chosen reference term; raw means <= 0 yield NaN and are skipped. exit_after ends the run.",
                    "vars"  : [
                        {"sym": r"\nu_i",                          "desc": "suggested scale factor to fold into weight_i"},
                        {"sym": r"\overline{\ell_i}",              "desc": "filtered mean raw value of term i"},
                        {"sym": r"\overline{\ell_{\mathrm{ref}}}", "desc": "filtered mean of the chosen reference term"},
                    ],
                },
            ],
        }

    def _training_optim(self) -> dict:
        """Returns the training-optimisation group: parameter-group rates, AdamW, warmup and schedules, clipping, EMA and stopping rules."""
        return {
            "group" : "Training · Optim",
            "blurb" : "Everything that moves the weights: per-group learning rates with an entry-point batch-size scaling rule, AdamW with decoupled decay, four warmup modes, six LR-schedule modes, gradient accumulation, four gradient-clipping modes (disabled, fixed, two adaptive), weight EMA, the VRAM-reservation guard, the overfit-check sanity gate, and the early-stopping / checkpoint rules. Note that the running defaults come from the flat TrainingQueueConfig via ConfigFactory, which overrides some bare sub-config dataclass defaults (scheduler horizon, patience, lr_scale).",
            "items" : [
                {
                    "title" : "Parameter group rates",
                    "tex"   : r"\eta_{\mathrm{enc}} = \eta_{\mathrm{bot}} = \eta_{\mathrm{dec}} = 3 \times 10^{-4}, \qquad \eta_{\mathrm{head}} = 10^{-3}, \qquad \lambda_{\bullet} = 10^{-4}",
                    "note"  : "The backbone config (ResUNetConfig for the default resunet) partitions parameters into encoder, bottleneck, decoder, and output_head groups with independent learning rates and weight decays, all fed to one torch.optim.AdamW. The training entry point (ConfigFactory) then sets optimizer.lr_scale = (batch_size / lr_reference_batch_size when scale_lr_with_batch is on, default on with reference batch size 256) * lr_multiplier (default 1.0, overwritten by the pre-training LR range test when pretrain.find_lr or the benchmark's find_lr probe runs), and every group's base LR is multiplied by this factor before the scheduler and warmup see it — the linear batch-size scaling rule times the probed multiplier.",
                    "vars"  : [
                        {"sym": r"\eta_{\mathrm{enc}}, \eta_{\mathrm{bot}}, \eta_{\mathrm{dec}}", "desc": "encoder, bottleneck, decoder learning rates (all 3e-4)"},
                        {"sym": r"\eta_{\mathrm{head}}",                                          "desc": "output-head learning rate (1e-3)"},
                        {"sym": r"\lambda_{\bullet}",                                             "desc": "per-group weight decay, same value (1e-4) for every group, set explicitly in get_param_groups"},
                    ],
                },
                {
                    "title" : "Linear warmup (default)",
                    "tex"   : r"f_{\mathrm{warmup}}(s) = \alpha_0 + (1 - \alpha_0)\cdot\frac{s}{S}",
                    "note"  : "Step-level ramp from the start factor to 1 over S optimiser steps, preventing early instability; holds at 1 permanently once s reaches S. This is the default warmup mode.",
                    "vars"  : [
                        {"sym": r"f_{\mathrm{warmup}}(s)", "desc": "LR multiplier at warmup step s"},
                        {"sym": r"s",                      "desc": "current warmup counter, incremented once per optimiser step"},
                        {"sym": r"S",                      "desc": "warmup_steps = 200"},
                        {"sym": r"\alpha_0",               "desc": "warmup_start_factor = 0.1 (hardcoded by ConfigFactory)"},
                    ],
                },
                {
                    "title" : "Cosine warmup",
                    "tex"   : r"f_{\mathrm{warmup}}(s) = \alpha_0 + (1 - \alpha_0)\cdot\frac{1 - \cos(\pi s / S)}{2}",
                    "note"  : "Smooth start and finish of the ramp; selected by warmup_mode = \"cosine\".",
                    "vars"  : [
                        {"sym": r"f_{\mathrm{warmup}}(s)", "desc": "LR multiplier at warmup step s"},
                        {"sym": r"s, S",                   "desc": "current warmup counter and total warmup steps"},
                        {"sym": r"\alpha_0",               "desc": "warmup start factor"},
                    ],
                },
                {
                    "title" : "Exponential warmup",
                    "tex"   : r"f_{\mathrm{warmup}}(s) = \alpha_0^{\,1 - s/S}",
                    "note"  : "Geometric ramp from the start factor; a non-positive start factor falls back to plain linear progress s/S. Selected by warmup_mode = \"exponential\".",
                    "vars"  : [
                        {"sym": r"f_{\mathrm{warmup}}(s)", "desc": "LR multiplier at warmup step s"},
                        {"sym": r"s, S",                   "desc": "current warmup counter and total warmup steps"},
                        {"sym": r"\alpha_0",               "desc": "warmup start factor"},
                    ],
                },
                {
                    "title" : "Polynomial warmup",
                    "tex"   : r"f_{\mathrm{warmup}}(s) = \alpha_0 + (1 - \alpha_0)\left(\frac{s}{S}\right)^{p}",
                    "note"  : "Power-shaped ramp; selected by warmup_mode = \"polynomial\".",
                    "vars"  : [
                        {"sym": r"f_{\mathrm{warmup}}(s)", "desc": "LR multiplier at warmup step s"},
                        {"sym": r"s, S",                   "desc": "current warmup counter and total warmup steps"},
                        {"sym": r"\alpha_0",               "desc": "warmup start factor"},
                        {"sym": r"p",                      "desc": "warmup_poly_power = 2.0"},
                    ],
                },
                {
                    "title" : "Scheduler — cosine annealing (default)",
                    "tex"   : r"F(t) = r + \frac{1}{2}(1 - r)\left(1 + \cos\!\left(\frac{\pi t}{T}\right)\right), \qquad r = \frac{\eta_{\min}}{\eta_0}",
                    "note"  : "Epoch-level multiplicative factor decaying along a cosine; progress t/T is capped at 1, holding the factor at the minimum ratio r past the horizon. Default scheduler.type.",
                    "vars"  : [
                        {"sym": r"F(t)",        "desc": "multiplicative LR factor at epoch t"},
                        {"sym": r"t",           "desc": "epoch index minus the curriculum offset"},
                        {"sym": r"T",           "desc": "annealing horizon = scheduler.epochs. The entry-point ConfigFactory installs scheduler.epochs = scheduler_epochs, or (when unset, the default) the training-epoch count epochs = 60. The bare SchedulerConfig standalone default is 100."},
                        {"sym": r"r",           "desc": "minimum-rate ratio"},
                        {"sym": r"\eta_{\min}", "desc": "minimum learning rate, eta_min = 1e-6"},
                        {"sym": r"\eta_0",      "desc": "base rate of the first parameter group (guarded by max(., 1e-12))"},
                    ],
                },
                {
                    "title" : "Scheduler — constant",
                    "tex"   : r"F(t) = 1",
                    "note"  : "The factor is 1 for every epoch, so the learning rate is driven by warmup alone and is constant once warmup finishes; this is the mode the overfit-check gate forces (scheduler.type = \"constant\"). _constant ignores the epoch entirely, so unlike the decaying schedules the curriculum epoch offset has no effect.",
                    "vars"  : [
                        {"sym": r"F(t)", "desc": "multiplicative LR factor (1 for all t)"},
                        {"sym": r"t",    "desc": "epoch index (ignored; _constant returns 1 regardless)"},
                    ],
                },
                {
                    "title" : "Scheduler — linear",
                    "tex"   : r"F(t) = 1 - (1 - r)\,\frac{t}{T}",
                    "note"  : "Epoch-level factor decaying linearly from 1 to the minimum-rate ratio r over T epochs; progress t/T capped at 1, holding at r afterwards.",
                    "vars"  : [
                        {"sym": r"F(t)", "desc": "multiplicative LR factor at epoch t"},
                        {"sym": r"t",    "desc": "epoch index minus the curriculum offset"},
                        {"sym": r"T",    "desc": "horizon = scheduler.epochs (entry-point default 60 = training epochs; SchedulerConfig standalone default 100)"},
                        {"sym": r"r",    "desc": "minimum-rate ratio, eta_min / eta_0"},
                    ],
                },
                {
                    "title" : "Scheduler — polynomial",
                    "tex"   : r"F(t) = r + (1 - r)\left(1 - \frac{t}{T}\right)^{p}",
                    "note"  : "Power-shaped decay from 1 to the minimum-rate ratio r, progress t/T capped at 1; with the default power 1 it coincides with the linear schedule.",
                    "vars"  : [
                        {"sym": r"F(t)", "desc": "multiplicative LR factor at epoch t"},
                        {"sym": r"t",    "desc": "epoch index minus the curriculum offset"},
                        {"sym": r"T",    "desc": "horizon = scheduler.epochs (entry-point default 60 = training epochs; SchedulerConfig standalone default 100)"},
                        {"sym": r"r",    "desc": "minimum-rate ratio, eta_min / eta_0"},
                        {"sym": r"p",    "desc": "scheduler.power = 1.0"},
                    ],
                },
                {
                    "title" : "Scheduler — exponential",
                    "tex"   : r"F(t) = \max(r, 10^{-8})^{\,t/T}",
                    "note"  : "Geometric decay of the factor from 1 toward the minimum-rate ratio, floored at 1e-8 to keep the base positive; progress t/T capped at 1.",
                    "vars"  : [
                        {"sym": r"F(t)", "desc": "multiplicative LR factor at epoch t"},
                        {"sym": r"t",    "desc": "epoch index minus the curriculum offset"},
                        {"sym": r"T",    "desc": "horizon = scheduler.epochs (entry-point default 60 = training epochs; SchedulerConfig standalone default 100)"},
                        {"sym": r"r",    "desc": "minimum-rate ratio, eta_min / eta_0"},
                    ],
                },
                {
                    "title" : "Scheduler — step",
                    "tex"   : r"F(t) = \max\!\left(\gamma^{\lfloor t / S_{\mathrm{step}} \rfloor},\ r\right)",
                    "note"  : "Staircase decay: the factor is multiplied by gamma every step_size epochs and floored at the minimum-rate ratio r. It uses the (curriculum-offset) epoch t directly in the floor division rather than normalising by a horizon, so unlike the other decaying schedules it never invokes the capped progress t/T.",
                    "vars"  : [
                        {"sym": r"F(t)",              "desc": "multiplicative LR factor at epoch t"},
                        {"sym": r"t",                 "desc": "epoch index minus the curriculum offset"},
                        {"sym": r"\gamma",            "desc": "scheduler.gamma = 0.1"},
                        {"sym": r"S_{\mathrm{step}}", "desc": "scheduler.step_size = 30 (floored at 1)"},
                        {"sym": r"r",                 "desc": "minimum-rate ratio, eta_min / eta_0"},
                    ],
                },
                {
                    "title" : "Combined effective learning rate",
                    "tex"   : r"\eta_{\mathrm{eff}} = \eta_0 \cdot F(t) \cdot f_{\mathrm{warmup}}(s)",
                    "note"  : "Scheduler factor per epoch times warmup factor per step, applied to every parameter group; after warmup finishes the second factor is 1. Here eta_0 is the (batch-size-scaled) base rate of the group.",
                    "vars"  : [
                        {"sym": r"\eta_{\mathrm{eff}}",    "desc": "learning rate applied to the optimiser"},
                        {"sym": r"\eta_0",                 "desc": "base rate of the parameter group (after lr_scale)"},
                        {"sym": r"F(t)",                   "desc": "scheduler factor at epoch t"},
                        {"sym": r"f_{\mathrm{warmup}}(s)", "desc": "warmup factor at step s (1 after warmup)"},
                    ],
                },
                {
                    "title" : "Gradient accumulation",
                    "tex"   : r"\mathcal{L}_{\mathrm{accum}} = \frac{\mathcal{L}_{\mathrm{total}}}{A}",
                    "note"  : "Each mini-batch loss is divided by the number of batches in its accumulation window; the optimiser steps once the window closes — every gradient_accumulation_steps batches, and again at epoch end — raising the effective batch size. Default gradient_accumulation_steps = 1 (no accumulation).",
                    "vars"  : [
                        {"sym": r"\mathcal{L}_{\mathrm{accum}}", "desc": "loss actually backpropagated"},
                        {"sym": r"\mathcal{L}_{\mathrm{total}}", "desc": "full batch loss"},
                        {"sym": r"A",                            "desc": "batches in the current accumulation window: min(gradient_accumulation_steps, n_batches - window_start), so the final short window divides by the remaining-batch count"},
                    ],
                },
                {
                    "title" : "Global gradient norm",
                    "tex"   : r"\|\mathbf{g}\|_2 = \sqrt{\sum_i \left\|\nabla_{\theta^{(i)}}\mathcal{L}\right\|_2^2}",
                    "note"  : "The 2-norm of the per-tensor gradient 2-norms, taken straight from the parameter grads. AMP is off by default (use_amp=False); when enabled it wraps the forward pass in torch.autocast(bfloat16), and since there is no GradScaler anywhere in the codebase the gradients are never scaled or unscaled. A warning fires above 100 (exploding-gradient heuristic).",
                    "vars"  : [
                        {"sym": r"\|\mathbf{g}\|_2",                 "desc": "global gradient norm of the whole model"},
                        {"sym": r"\nabla_{\theta^{(i)}}\mathcal{L}", "desc": "loss gradient w.r.t. parameter tensor i"},
                    ],
                },
                {
                    "title" : "Clipping rule",
                    "tex"   : r"\mathbf{g}^{(i)} \leftarrow \mathbf{g}^{(i)} \cdot \min\!\left(1,\ \frac{\tau}{\|\mathbf{g}\|_2}\right)",
                    "note"  : "All gradients are scaled by a common factor so the global norm never exceeds the threshold; a 1e-6 stabiliser guards the division and the clip ratio is logged per step. The \"disabled\" mode returns the norm untouched (no clip). Default mode is \"fixed\".",
                    "vars"  : [
                        {"sym": r"\mathbf{g}^{(i)}", "desc": "gradient of parameter tensor i"},
                        {"sym": r"\tau",             "desc": "threshold; fixed mode: max_grad_norm = 1.0"},
                        {"sym": r"\|\mathbf{g}\|_2", "desc": "global gradient norm"},
                    ],
                },
                {
                    "title" : "Adaptive clip thresholds",
                    "tex"   : r"\tau = P_q\!\left(\|\mathbf{g}\|_2^{(t-W:t)}\right) \qquad \text{or} \qquad \tau = \bar{g} + k\,\sigma_g",
                    "note"  : "adaptive_percentile takes a percentile of the last W recorded norms; adaptive_mean_std takes mean plus k standard deviations. No clipping occurs until the recorded-norm history reaches W entries.",
                    "vars"  : [
                        {"sym": r"\tau",                       "desc": "adaptive clipping threshold"},
                        {"sym": r"P_q",                        "desc": "q-th percentile, adaptive_percentile = 95"},
                        {"sym": r"\|\mathbf{g}\|_2^{(t-W:t)}", "desc": "the last W recorded gradient norms"},
                        {"sym": r"W",                          "desc": "adaptive_window = 200"},
                        {"sym": r"\bar{g}, \sigma_g",          "desc": "mean and std of the window"},
                        {"sym": r"k",                          "desc": "adaptive_mean_std_k = 2.0"},
                    ],
                },
                {
                    "title" : "AdamW moment estimates",
                    "tex"   : r"m_t = \beta_1 m_{t-1} + (1-\beta_1)\,g_t, \qquad v_t = \beta_2 v_{t-1} + (1-\beta_2)\,g_t^2",
                    "note"  : "Exponential moving averages of the gradient and its square, per parameter (standard torch.optim.AdamW).",
                    "vars"  : [
                        {"sym": r"m_t",              "desc": "first moment estimate at step t"},
                        {"sym": r"v_t",              "desc": "second moment estimate at step t"},
                        {"sym": r"g_t",              "desc": "gradient at step t"},
                        {"sym": r"t",                "desc": "optimiser step"},
                        {"sym": r"\beta_1, \beta_2", "desc": "moment decay coefficients, optimizer.betas = (0.9, 0.999)"},
                    ],
                },
                {
                    "title" : "AdamW decoupled update",
                    "tex"   : r"\theta_{t+1} = \theta_t - \eta\left(\frac{\hat{m}_t}{\sqrt{\hat{v}_t}+\epsilon} + \lambda\theta_t\right), \qquad \hat{m}_t = \frac{m_t}{1-\beta_1^t}, \qquad \hat{v}_t = \frac{v_t}{1-\beta_2^t}",
                    "note"  : "Bias-corrected moments with weight decay decoupled from the gradient path. Lambda is the per-group weight decay set in get_param_groups (1e-4); the OptimizerConfig.weight_decay default (0.1) is only a setdefault fallback for groups that omit it, which the backbone groups never do.",
                    "vars"  : [
                        {"sym": r"\theta_t",             "desc": "parameter value at step t"},
                        {"sym": r"\eta",                 "desc": "learning rate of the parameter group"},
                        {"sym": r"\hat{m}_t, \hat{v}_t", "desc": "bias-corrected first and second moments"},
                        {"sym": r"\beta_1^t, \beta_2^t", "desc": "decay factors to the power t"},
                        {"sym": r"\lambda",              "desc": "per-group weight decay (1e-4)"},
                        {"sym": r"\epsilon",             "desc": "optimizer.eps = 1e-8"},
                    ],
                },
                {
                    "title" : "Weight EMA",
                    "tex"   : r"\theta^{\mathrm{ema}}_t = \rho\,\theta^{\mathrm{ema}}_{t-1} + (1 - \rho)\,\theta_t",
                    "note"  : "Optional exponential moving average of every parameter, updated after each optimiser step; the averaged weights are swapped in for validation, reconstruction figures, and test evaluation (via the checkpoint, since the best checkpoint is itself saved under the EMA-applied validation context), then the live weights are restored. Off by default (use_ema).",
                    "vars"  : [
                        {"sym": r"\theta^{\mathrm{ema}}_t", "desc": "shadow (averaged) weight after step t"},
                        {"sym": r"\theta_t",                "desc": "live parameter after the optimiser step"},
                        {"sym": r"\rho",                    "desc": "ema_decay = 0.999"},
                    ],
                },
                {
                    "title" : "Early stopping",
                    "tex"   : r"\text{improved} \iff \ell_{\mathrm{val}} < \ell^{*}_{\mathrm{val}} - \delta, \qquad \text{stop} \iff \mathrm{counter} \geq P",
                    "note"  : "Improvement requires beating the running best by more than min_delta (delta = 0 by default, i.e. strict improvement); the counter resets on improvement and increments otherwise, stopping when it reaches the patience. The checkpoint separately persists the best weights on a strict val_loss < best test (no min_delta margin); on stop, weights revert to the best checkpoint when restore_best is set (default True).",
                    "vars"  : [
                        {"sym": r"\ell_{\mathrm{val}}",     "desc": "validation loss of the current epoch"},
                        {"sym": r"\ell^{*}_{\mathrm{val}}", "desc": "best validation loss so far"},
                        {"sym": r"\delta",                  "desc": "min_delta = 0.0"},
                        {"sym": r"\mathrm{counter}",        "desc": "consecutive validations without improvement"},
                        {"sym": r"P",                       "desc": "patience. Entry-point default 30 (ConfigFactory sets early_stopping.patience = early_stop_patience = 30); the bare EarlyStoppingConfig standalone default is 15."},
                    ],
                },
                {
                    "title" : "VRAM reservation",
                    "tex"   : r"B_{\mathrm{park}} \approx B_{\mathrm{free}} - B_{\mathrm{keep}}",
                    "note"  : "When reserve_vram is set, before training and after every cache clear the spare device memory above the keep-free target is claimed as uint8 tensors (2 MiB-aligned, 16 MiB chunk floor, halving the chunk size on out-of-memory) and immediately freed, parking it in the CUDA caching allocator so other users on the GPU cannot grab it. Off by default and no-op on CPU.",
                    "vars"  : [
                        {"sym": r"B_{\mathrm{park}}", "desc": "bytes parked in the allocator cache"},
                        {"sym": r"B_{\mathrm{free}}", "desc": "currently-free device memory"},
                        {"sym": r"B_{\mathrm{keep}}", "desc": "keep-free target, vram_keep_free_gb = 1.0 GB"},
                    ],
                },
                {
                    "title" : "Overfit-check gate",
                    "tex"   : r"\mathrm{pass} \iff \ell_{\min} \leq \ell_{\mathrm{stop}} \ \ \lor \ \ \frac{\ell_{\min}}{\ell_0} \leq \rho",
                    "note"  : "Optional pre-training sanity gate: a regularization-stripped clone (weight decay, dropout, stochastic depth and per-group *_wd zeroed, warmup and EMA off, constant LR, curriculum disabled and active-normalization off) memorizes n_examples = 2 training patches (augmentation off) for up to max_steps = 300 (12 epochs of 25 steps). It passes if the best training loss reaches the stop threshold or falls to a fraction rho of the initial loss, otherwise it raises RuntimeError and aborts the run; the verdict is written to meta/overfit_report.json. Off by default.",
                    "vars"  : [
                        {"sym": r"\ell_{\min}",          "desc": "best training loss over the gate run"},
                        {"sym": r"\ell_0",               "desc": "initial gate training loss"},
                        {"sym": r"\ell_{\mathrm{stop}}", "desc": "stop_threshold = 1e-6"},
                        {"sym": r"\rho",                 "desc": "pass_loss_ratio = 0.05"},
                    ],
                },
            ],
        }

    def _inference(self) -> dict:
        """Returns the inference group: de-normalisation, cube assembly, scoring metrics and data-consistency checks."""
        return {
            "group" : "Inference",
            "blurb" : "Patch predictions are de-normalised and physically clamped, then assembled into dense cubes (curves by weighted overlap-add, Gaussian parameters by centrality winner-take-all) and scored against the ground truth by curve, parameter, and permutation-invariant matched-Gaussian metrics, an optional reduced-Capon baseline comparison, and interferometric data-consistency checks that also diagnose the Capon elevation sign.",
            "items" : [
                {
                    "title" : "Prediction de-normalisation and physical clamp",
                    "tex"   : r"\hat{p} = \mathrm{denorm}\!\left(\hat{p}_{\mathrm{raw}}\right); \quad \hat{a}_k \leftarrow \mathrm{clip}\!\left(\hat{a}_k,\ 0,\ a_{\max}\right),\ \ \hat{\mu}_k \leftarrow \mathrm{clip}\!\left(\hat{\mu}_k,\ x_{\min},\ x_{\max}\right),\ \ \hat{\sigma}_k \leftarrow \mathrm{clip}\!\left(\hat{\sigma}_k,\ \tfrac{\Delta x}{2},\ \tfrac{x_{\max}-x_{\min}}{2}\right)",
                    "note"  : "Model outputs are de-normalised to physical scale, then every Gaussian is hard-clamped (leaky_slope = 0 at inference) to non-negative amplitude at most amp_max, mean inside the elevation axis, and spread between half a bin and half the axis span; ground-truth parameters are de-normalised only, never clamped (model_wrapper.py denormalize_output with GaussianClamp.apply leaky_slope=0.0; predictor.py denorms GT via the plain Normalizer).",
                    "vars"  : [
                        {"sym": r"\hat{a}_k, \hat{\mu}_k, \hat{\sigma}_k", "desc": "predicted amplitude, mean, spread of slot k"},
                        {"sym": r"a_{\max}",                               "desc": "amp_max from the training normalisation stats (norm_stats.clamp.amp_max)"},
                        {"sym": r"x_{\min}, x_{\max}",                     "desc": "elevation-axis extremes"},
                        {"sym": r"\Delta x",                               "desc": "elevation-axis step, x_step = (x_max - x_min)/(len-1)"},
                    ],
                },
                {
                    "title" : "GT slot alignment",
                    "tex"   : r"\kappa_k = \begin{cases} +\infty & a^{\mathrm{GT}}_k < 10^{-4} \\ \mu^{\mathrm{GT}}_k & \text{otherwise} \end{cases}, \qquad \mathrm{GT} \leftarrow \mathrm{take}\!\left(\mathrm{GT},\ \operatorname{argsort}_k \kappa_k\right)",
                    "note"  : "GT components are mu-sorted with inactive slots pushed last; a slot counts as active under ParamMatcher.is_active, amplitude >= ACTIVE_AMP_THR = 1e-4. Predictions keep their raw slot order (predictor.py _cpu_worker).",
                    "vars"  : [
                        {"sym": r"\kappa_k",            "desc": "sort key of GT slot k"},
                        {"sym": r"a^{\mathrm{GT}}_k",   "desc": "GT amplitude of slot k (physical scale)"},
                        {"sym": r"\mu^{\mathrm{GT}}_k", "desc": "GT mean elevation of slot k"},
                        {"sym": r"\mathrm{take}",       "desc": "reorder of the GT slots by the argsort"},
                    ],
                },
                {
                    "title" : "Curve reconstruction",
                    "tex"   : r"\hat{y}_{b,n,h,w} = \sum_{k=1}^{K} \hat{a}_{k}\,\exp\!\left(-\frac{(x_n - \hat{\mu}_{k})^2}{2\,\hat{\sigma}_{k}^2}\right)",
                    "note"  : "Inference-side reconstruction sums rectified-amplitude Gaussians (GaussianReconstructor.reconstruct_batch in tools/data/gaussians.py, called from predictor.py _cpu_worker); amplitudes are rectified at 0 and the denominator stabilised as 2*sig*sig+1e-8 in code. The GT curve uses the same kernel on the mu-sorted parameters.",
                    "vars"  : [
                        {"sym": r"\hat{y}_{b,n,h,w}",                      "desc": "reconstructed curve at bin n, pixel (h, w), sample b"},
                        {"sym": r"x_n",                                    "desc": "elevation axis sample (m)"},
                        {"sym": r"\hat{a}_k, \hat{\mu}_k, \hat{\sigma}_k", "desc": "predicted parameters of slot k"},
                        {"sym": r"K",                                      "desc": "number of Gaussian slots"},
                    ],
                },
                {
                    "title" : "Hann window",
                    "tex"   : r"w_v[i] = 0.5 - 0.5\cos\!\left(\frac{2\pi(i + 0.5)}{P_H}\right)",
                    "note"  : "The default per-axis profile for the curve stitcher; de-emphasises patch borders in favour of centres, suppressing seams at overlaps. The horizontal profile is the same expression over P_W, since patches are rectangular.",
                    "vars"  : [
                        {"sym": r"w_v[i]", "desc": "vertical window weight at offset i"},
                        {"sym": r"i",      "desc": "pixel offset within the patch, 0 to P_H-1"},
                        {"sym": r"P_H",    "desc": "patch height (the horizontal profile uses P_W)"},
                    ],
                },
                {
                    "title" : "Triangular and uniform windows, 2D assembly",
                    "tex"   : r"w_v[i] = 1 - \left|\frac{2(i + 0.5)}{P_H} - 1\right|, \qquad w = w_v \otimes w_h, \qquad w_{\mathrm{uniform}} = \mathbf{1}^{P_H \times P_W}",
                    "note"  : "Per-axis factors are floored at 1e-3 before the outer product, guaranteeing strictly positive weights at every covered position.",
                    "vars"  : [
                        {"sym": r"w_v, w_h", "desc": "vertical and horizontal axis profiles, of length P_H and P_W"},
                        {"sym": r"w",        "desc": "2D patch weighting window"},
                        {"sym": r"\otimes",  "desc": "outer product"},
                        {"sym": r"P_H, P_W", "desc": "patch height and width"},
                    ],
                },
                {
                    "title" : "Overlap-add accumulation",
                    "tex"   : r"A[:,\,v_0{:}v_0{+}P_H,\ h_0{:}h_0{+}P_W] \mathrel{+}= p \cdot w, \qquad W[v_0{:}v_0{+}P_H,\ h_0{:}h_0{+}P_W] \mathrel{+}= w",
                    "note"  : "Every curve patch is scattered into a weighted accumulator at its grid position, alongside a matching weight accumulator (predictor.py CubeStitcher.add_patch).",
                    "vars"  : [
                        {"sym": r"A",          "desc": "value accumulator, shape (C, H_pad, W_pad)"},
                        {"sym": r"W",          "desc": "weight accumulator, shape (H_pad, W_pad)"},
                        {"sym": r"p",          "desc": "patch output, shape (C, P_H, P_W)"},
                        {"sym": r"w",          "desc": "2D patch weighting window"},
                        {"sym": r"(v_0, h_0)", "desc": "patch top-left position in the padded grid"},
                    ],
                },
                {
                    "title" : "Cube finalisation",
                    "tex"   : r"\hat{C}[:, h, w] = \frac{A[:,\,h + p_t,\ w + p_l]}{W[h + p_t,\ w + p_l]}",
                    "note"  : "Accumulated values divided by accumulated weights, then trimmed of grid padding; if any covered-region pixel has zero accumulated weight the stitcher raises ValueError, since the patch grid must fully tile the split region (predictor.py CubeStitcher.finalize_cube).",
                    "vars"  : [
                        {"sym": r"\hat{C}",  "desc": "final stitched curve cube"},
                        {"sym": r"A, W",     "desc": "value and weight accumulators"},
                        {"sym": r"(h, w)",   "desc": "pixel position in the trimmed cube"},
                        {"sym": r"p_t, p_l", "desc": "top and left padding offsets"},
                    ],
                },
                {
                    "title" : "Parameter cube assembly (centrality winner-take-all)",
                    "tex"   : r"\hat{P}[:, h, w] = p^{(k^\star)}[:, h, w], \qquad k^\star = \operatorname*{arg\,max}_{k \,:\, (h,w)\,\in\,\Omega_k} w^{\mathrm{hann}}\!\left[h - v_0^{(k)},\ w - h_0^{(k)}\right]",
                    "note"  : "The predicted and GT Gaussian-parameter cubes are NOT overlap-added (averaging slot parameters across patches is meaningless); each covered pixel keeps the parameter vector of whichever overlapping patch covers it most centrally, measured by a Hann window that is always used regardless of cfg.stitch_window. Replacement is strictly-greater (take = centrality > best), so ties keep the earlier-processed patch, and any uncovered pixel raises (predictor.py SelectStitcher.add_patch/finalize_cube).",
                    "vars"  : [
                        {"sym": r"\hat{P}",                "desc": "stitched parameter cube (predicted or GT)"},
                        {"sym": r"p^{(k)}",                "desc": "parameter output of patch k"},
                        {"sym": r"w^{\mathrm{hann}}",      "desc": "Hann centrality window (hardcoded, independent of cfg.stitch_window)"},
                        {"sym": r"\Omega_k",               "desc": "pixels covered by patch k"},
                        {"sym": r"(v_0^{(k)}, h_0^{(k)})", "desc": "top-left grid position of patch k"},
                    ],
                },
                {
                    "title" : "Placeholder masking in the GT cube",
                    "tex"   : r"\mu^{\mathrm{GT}}_k,\ \sigma^{\mathrm{GT}}_k \leftarrow \mathrm{NaN} \quad \text{where } a^{\mathrm{GT}}_k < 10^{-4}",
                    "note"  : "After stitching, mu and sigma of GT slots that fail ParamMatcher.is_active (amplitude below ACTIVE_AMP_THR = 1e-4) are set to NaN so downstream statistics skip inactive slots (predictor.py _finalize_results).",
                    "vars"  : [
                        {"sym": r"a^{\mathrm{GT}}_k",                           "desc": "stitched GT amplitude of slot k"},
                        {"sym": r"\mu^{\mathrm{GT}}_k, \sigma^{\mathrm{GT}}_k", "desc": "GT mean and spread of slot k"},
                    ],
                },
                {
                    "title" : "Per-pixel MSE and MAE",
                    "tex"   : r"\mathrm{MSE}_{h,w} = \frac{1}{N}\sum_n \left(\hat{y} - y\right)^2, \qquad \mathrm{MAE}_{h,w} = \frac{1}{N}\sum_n \left|\hat{y} - y\right|",
                    "note"  : "Computed once on the fully stitched curve cubes over the elevation axis (axis 0), not per patch; metrics.py Metrics.curve_pixel_metrics, invoked from predictor.py _finalize_results.",
                    "vars"  : [
                        {"sym": r"\hat{y}, y", "desc": "predicted and GT curve values"},
                        {"sym": r"N",          "desc": "number of elevation bins"},
                        {"sym": r"h, w",       "desc": "pixel (azimuth, range) indices"},
                    ],
                },
                {
                    "title" : "Per-pixel R²",
                    "tex"   : r"R^2_{h,w} = 1 - \frac{\sum_n (\hat{y} - y)^2}{\sum_n (y - \bar{y}_{h,w})^2}",
                    "note"  : "Coefficient of determination of each pixel's elevation profile computed on the stitched cubes; a 1e-12 stabiliser guards the denominator (tools/metrics/scoring.py R2.pixel_map).",
                    "vars"  : [
                        {"sym": r"\hat{y}, y",    "desc": "predicted and GT curve values"},
                        {"sym": r"\bar{y}_{h,w}", "desc": "mean GT over elevation at the pixel"},
                        {"sym": r"n",             "desc": "elevation bin index"},
                    ],
                },
                {
                    "title" : "Per-pixel cosine similarity and peak error",
                    "tex"   : r"\mathrm{CosSim}_{h,w} = \frac{\sum_n \hat{y}\,y}{\|\hat{y}\|_2\,\|y\|_2}, \qquad \mathrm{PeakErr}_{h,w} = \left|\operatorname{argmax}_n \hat{y} - \operatorname{argmax}_n y\right|",
                    "note"  : "Profile shape agreement and displacement of the dominant scatterer in elevation bins, computed on the stitched cubes; each L2 norm carries a 1e-8 stabiliser in code (metrics.py curve_pixel_metrics).",
                    "vars"  : [
                        {"sym": r"\hat{y}, y",              "desc": "predicted and GT elevation profiles"},
                        {"sym": r"\|\cdot\|_2",             "desc": "L2 norm over the elevation axis"},
                        {"sym": r"\operatorname{argmax}_n", "desc": "bin index of the profile maximum"},
                    ],
                },
                {
                    "title" : "Global curve MSE, MAE, RMSE",
                    "tex"   : r"\mathrm{MSE} = \frac{1}{N_e A_z R_g}\sum_{n,a,r}\left(\hat{Y} - Y\right)^2, \qquad \mathrm{MAE} = \frac{1}{N_e A_z R_g}\sum_{n,a,r}\left|\hat{Y} - Y\right|, \qquad \mathrm{RMSE} = \sqrt{\mathrm{MSE}}",
                    "note"  : "Computed on the stitched cubes at physical scale in float64 (metrics.py _curve_scalar_metrics).",
                    "vars"  : [
                        {"sym": r"\hat{Y}, Y", "desc": "predicted and GT spectrum cubes"},
                        {"sym": r"N_e",        "desc": "number of elevation bins"},
                        {"sym": r"A_z, R_g",   "desc": "azimuth and range extents (pixels)"},
                        {"sym": r"n, a, r",    "desc": "elevation, azimuth, range indices"},
                    ],
                },
                {
                    "title" : "Overall R²",
                    "tex"   : r"R^2_{\mathrm{overall}} = 1 - \frac{\sum_{n,a,r}(\hat{Y} - Y)^2}{\sum_{n,a,r}(Y - \bar{Y})^2}",
                    "note"  : "Single-figure reconstruction quality over the entire cube; a 1e-12 stabiliser guards the denominator.",
                    "vars"  : [
                        {"sym": r"\hat{Y}, Y", "desc": "predicted and GT spectrum cubes"},
                        {"sym": r"\bar{Y}",    "desc": "global mean of the GT cube"},
                        {"sym": r"n, a, r",    "desc": "elevation, azimuth, range indices"},
                    ],
                },
                {
                    "title" : "PSNR",
                    "tex"   : r"\mathrm{PSNR} = 10\,\log_{10}\!\left(\frac{(Y_{\max} - Y_{\min})^2}{\mathrm{MSE}}\right)",
                    "note"  : "Peak signal is the dynamic range of the ground truth only; the prediction never enters the numerator. Returns infinity at zero MSE and NaN at zero GT range.",
                    "vars"  : [
                        {"sym": r"Y_{\max}, Y_{\min}", "desc": "extrema of the GT cube"},
                        {"sym": r"\mathrm{MSE}",       "desc": "global curve MSE"},
                    ],
                },
                {
                    "title" : "Map statistics and percentiles",
                    "tex"   : r"\{\mathrm{mean}, \mathrm{std}, \mathrm{median}, \min, \max\} \quad \text{and} \quad P_q,\ q \in \{1, 5, 25, 50, 75, 95, 99\}",
                    "note"  : "Every per-pixel map (MSE, MAE, R², cosine, peak error) is summarised by basic statistics and seven percentiles.",
                    "vars"  : [
                        {"sym": r"P_q", "desc": "q-th percentile of the flattened map"},
                        {"sym": r"q",   "desc": "percentile level"},
                    ],
                },
                {
                    "title" : "Peak error in metres",
                    "tex"   : r"\mathrm{PeakErr}_{\mathrm{m}} = \mathrm{PeakErr}_{\mathrm{bins}} \cdot \Delta x",
                    "note"  : "Mean, median, and 95th percentile of the peak displacement are also reported in physical units (metrics.py compute).",
                    "vars"  : [
                        {"sym": r"\mathrm{PeakErr}_{\mathrm{bins}}", "desc": "peak displacement in elevation bins"},
                        {"sym": r"\Delta x",                         "desc": "elevation axis step (m)"},
                    ],
                },
                {
                    "title" : "Per-elevation MAE and RMSE",
                    "tex"   : r"\mathrm{MAE}(n) = \frac{1}{A_z R_g}\sum_{a,r}\left|\hat{Y}_{n,a,r} - Y_{n,a,r}\right|, \qquad \mathrm{RMSE}(n) = \sqrt{\frac{1}{A_z R_g}\sum_{a,r}(\hat{Y}_{n,a,r} - Y_{n,a,r})^2}",
                    "note"  : "Each elevation bin scored across all pixels, isolating heights the model reconstructs poorly (metrics.py _elev_metrics).",
                    "vars"  : [
                        {"sym": r"\hat{Y}, Y", "desc": "predicted and GT spectrum cubes"},
                        {"sym": r"n",          "desc": "elevation bin index"},
                        {"sym": r"A_z, R_g",   "desc": "azimuth and range extents"},
                        {"sym": r"a, r",       "desc": "azimuth and range indices"},
                    ],
                },
                {
                    "title" : "Per-elevation R²",
                    "tex"   : r"R^2(n) = 1 - \frac{\sum_{a,r}(\hat{Y}_{n,a,r} - Y_{n,a,r})^2}{\sum_{a,r}(Y_{n,a,r} - \bar{Y}_n)^2}",
                    "note"  : "Per-bin coefficient of determination, treating all pixels of one height as samples; a 1e-12 stabiliser guards the denominator.",
                    "vars"  : [
                        {"sym": r"\hat{Y}, Y", "desc": "predicted and GT spectrum cubes"},
                        {"sym": r"\bar{Y}_n",  "desc": "mean GT at elevation bin n"},
                        {"sym": r"a, r",       "desc": "azimuth and range indices"},
                    ],
                },
                {
                    "title" : "Per-elevation cross-entropy",
                    "tex"   : r"\mathrm{CE}(n) = -\frac{1}{A_z R_g}\sum_{a,r} \bar{p}^{\mathrm{GT}}_{n,a,r}\,\log \bar{p}^{\mathrm{pred}}_{n,a,r}, \qquad \bar{p}_{n,a,r} = \frac{Y_{n,a,r}}{\sum_n Y_{n,a,r}}",
                    "note"  : "Treats each pixel's profile as a probability distribution over elevation (column-normalised over axis 0); probabilities and column sums are clipped at 1e-12 in code.",
                    "vars"  : [
                        {"sym": r"\mathrm{CE}(n)",                                 "desc": "cross-entropy at elevation bin n"},
                        {"sym": r"\bar{p}^{\mathrm{GT}}, \bar{p}^{\mathrm{pred}}", "desc": "column-normalised GT and predicted probabilities"},
                        {"sym": r"Y_{n,a,r}",                                      "desc": "cube value at bin n, pixel (a, r)"},
                    ],
                },
                {
                    "title" : "Slice SSIM window",
                    "tex"   : r"\mathrm{win} = \min\!\left(7,\ \mathrm{odd}\!\left(\min(H_s, W_s)\right)\right)",
                    "note"  : "skimage SSIM is computed per slice along elevation, range, and azimuth with an adaptive odd window of at most 7.",
                    "vars"  : [
                        {"sym": r"\mathrm{win}",    "desc": "SSIM window side"},
                        {"sym": r"H_s, W_s",        "desc": "spatial dimensions of the slice"},
                        {"sym": r"\mathrm{odd}(m)", "desc": "m if odd, else m - 1"},
                    ],
                },
                {
                    "title" : "Slice SSIM index",
                    "tex"   : r"\mathrm{SSIM}_{\mathrm{slice}}(i) = \frac{1}{|\Omega|}\sum_{p \in \Omega} \frac{(2\mu_{\hat{s},p}\,\mu_{s^*,p} + C_1)(2\sigma_{\hat{s}s^*,p} + C_2)}{(\mu_{\hat{s},p}^2 + \mu_{s^*,p}^2 + C_1)(\sigma_{\hat{s},p}^2 + \sigma_{s^*,p}^2 + C_2)}",
                    "note"  : "Mean of the local windowed index over the slice; the data range is taken from the GT slice only. compute() runs SSIM twice: once on the raw cubes (prefix 'gt') and once on unit-area-normalised cubes (prefix 'norm'); per-axis means aggregate the finite slice values.",
                    "vars"  : [
                        {"sym": r"i",                                      "desc": "slice index along the chosen axis"},
                        {"sym": r"\Omega",                                 "desc": "set of local window centres; |Ω| its size"},
                        {"sym": r"p",                                      "desc": "a window centre"},
                        {"sym": r"\mu_{\hat{s},p}, \mu_{s^*,p}",           "desc": "local means of predicted and GT slices"},
                        {"sym": r"\sigma_{\hat{s},p}^2, \sigma_{s^*,p}^2", "desc": "local variances"},
                        {"sym": r"\sigma_{\hat{s}s^*,p}",                  "desc": "local covariance"},
                        {"sym": r"C_1, C_2",                               "desc": "(k1·L)² and (k2·L)², k1 = 0.01, k2 = 0.03"},
                        {"sym": r"L",                                      "desc": "GT slice max minus min"},
                    ],
                },
                {
                    "title" : "Permutation cost and optimal assignment",
                    "tex"   : r"C_{ij} = \left|\hat{\mu}_i - \mu^{\mathrm{GT}}_j\right|, \qquad \pi^*_{a,r} = \operatorname*{arg\,min}_{\pi \in S_K} \sum_k C_{k,\pi(k)}",
                    "note"  : "Inactive pairs and NaN/posinf entries take a large cost (1e7) so only mutually-active slots (amp >= ParamMatcher.ACTIVE_AMP_THR = 1e-4) match cheaply. The optimum is found by exhaustively enumerating all K! permutations for every K (no Hungarian fallback), in pixel chunks of 250000 (gaussian_matching.py GaussianMatcher).",
                    "vars"  : [
                        {"sym": r"C_{ij}",              "desc": "cost of matching predicted slot i to GT slot j"},
                        {"sym": r"\hat{\mu}_i",         "desc": "predicted mean of slot i (raw slot order)"},
                        {"sym": r"\mu^{\mathrm{GT}}_j", "desc": "GT mean of slot j (mu-sorted)"},
                        {"sym": r"\pi^*_{a,r}",         "desc": "cost-minimising assignment at pixel (a, r)"},
                        {"sym": r"S_K",                 "desc": "all K! slot permutations"},
                    ],
                },
                {
                    "title" : "Matched Gaussian parameter metrics",
                    "tex"   : r"\mathrm{MAE}_\mu = \frac{1}{|\mathcal{M}|}\sum_{(i,j)\in\mathcal{M}} \left|\hat{\mu}_i - \mu^{\mathrm{GT}}_j\right|, \qquad F_1 = \frac{2\,\mathrm{Prec}\cdot\mathrm{Rec}}{\mathrm{Prec}+\mathrm{Rec}}, \qquad \mathrm{TP} = \left\{(i,j)\in\mathcal{M} : |\Delta\mu| \le \tau\right\}",
                    "note"  : "On active pixels the matched pairs from the optimal assignment give mu and sigma MAE/RMSE; detection precision, recall, and F1 count a true positive when the matched mean error is within the tolerance. Also bucketed by GT active count (metrics.py matched_gaussian_metrics).",
                    "vars"  : [
                        {"sym": r"\mathcal{M}",                 "desc": "set of matched mutually-active pred-GT pairs"},
                        {"sym": r"\mathrm{MAE}_\mu",            "desc": "mean absolute mean-elevation error over matched pairs (m)"},
                        {"sym": r"\mathrm{Prec}, \mathrm{Rec}", "desc": "TP / pred-active and TP / GT-active"},
                        {"sym": r"\tau",                        "desc": "match tolerance on |Δμ|, match_tol = 5.0 (elevation-axis units, same as μ)"},
                    ],
                },
                {
                    "title" : "Gaussian active-count accuracy",
                    "tex"   : r"c^{s}_{a,r} = \sum_{k=1}^{K} \mathbb{1}\!\left[a^{s}_k \ge \tau_a\right], \qquad \mathrm{ExactFrac} = \frac{1}{HW}\sum_{a,r}\mathbb{1}\!\left[c^{\mathrm{pred}}_{a,r} = c^{\mathrm{GT}}_{a,r}\right], \qquad \mathrm{Acc}_{\mathrm{gt}=k} = \Pr\!\left(c^{\mathrm{pred}} = k \mid c^{\mathrm{GT}} = k\right)",
                    "note"  : "Active Gaussians (amplitude at or above 1e-4) are counted per pixel for prediction and GT; the run reports exact/under/over count fractions, overall and per-slot active fractions (the predicted per-slot fraction uses the GT-aligned assignment), and exact-count accuracy conditioned on the GT active count (count_acc_gt{k}) and also on the predicted count (count_acc_pred{k}) (metrics.py _active_count_stats).",
                    "vars"  : [
                        {"sym": r"c^{s}_{a,r}",                  "desc": "per-pixel active-Gaussian count for source s (pred or GT)"},
                        {"sym": r"\tau_a",                       "desc": "active-amplitude threshold, ParamMatcher.is_active with ACTIVE_AMP_THR = 1e-4"},
                        {"sym": r"\mathrm{ExactFrac}",           "desc": "fraction of pixels whose predicted and GT counts match"},
                        {"sym": r"\mathrm{Acc}_{\mathrm{gt}=k}", "desc": "exact-count accuracy among pixels with k active GT slots"},
                    ],
                },
                {
                    "title" : "Slot-organisation diagonality and usage entropy",
                    "tex"   : r"H_{\mathrm{slot}} = \frac{-\sum_k q_k \log q_k}{\log K}, \quad q_k = \frac{u_k}{\sum_j u_j}, \qquad D(\mathbf{N}) = \frac{\operatorname{tr}\mathbf{N}}{\sum_{ij} N_{ij}}",
                    "note"  : "Predicted slot usage is summarised by a normalised usage entropy; two diagonality scores measure how consistently each predicted slot holds its elevation-rank position (slot_mu_rank_diag) and matches the same-index GT slot under the optimal assignment (slot_gt_alignment), each the trace fraction of a K×K count matrix (metrics.py _slot_organization_stats, tools/metrics/slot_organization.py).",
                    "vars"  : [
                        {"sym": r"H_{\mathrm{slot}}", "desc": "normalised entropy of predicted slot usage"},
                        {"sym": r"u_k",               "desc": "fraction of pixels where slot k is active (amp >= 1e-4)"},
                        {"sym": r"q_k",               "desc": "usage-normalised weight of slot k"},
                        {"sym": r"\mathbf{N}",        "desc": "K×K count matrix (mu-rank occupancy or pred->GT assignment)"},
                        {"sym": r"D",                 "desc": "diagonal-mass fraction, trace over total"},
                    ],
                },
                {
                    "title" : "Reduced-baseline Capon improvement",
                    "tex"   : r"\bar{y}_{n,a,r} = \frac{y_{n,a,r}}{\max\!\left(\sum_n y_{n,a,r},\,10^{-12}\right)}\ \ (y\in\{C,\hat{C},\mathbf{r}\}), \qquad \Delta_{a,r} = \mathrm{MSE}^{\mathrm{red}}_{a,r} - \mathrm{MSE}^{\mathrm{pred}}_{a,r}",
                    "note"  : "When the run used a strict secondary subset, a reduced Capon tomogram is re-synthesised; GT, prediction, and reduced cubes are unit-area normalised, then the per-pixel MSE improvement of the network over the reduced baseline (positive where the network wins) is reported alongside its curve, SSIM and per-elevation metrics (metrics.py reduced_comparison).",
                    "vars"  : [
                        {"sym": r"\bar{y}",                "desc": "unit-area-normalised profile (GT, prediction, or reduced)"},
                        {"sym": r"C, \hat{C}, \mathbf{r}", "desc": "GT, prediction, and reduced-Capon cubes"},
                        {"sym": r"\Delta_{a,r}",           "desc": "reduced-minus-prediction per-pixel MSE improvement"},
                    ],
                },
                {
                    "title" : "Reduced-baseline orientation check",
                    "tex"   : r"\rho_{\mathrm{aligned}} = \frac{\langle g,\, r\rangle}{\|g\|\,\|r\| + 10^{-12}}, \qquad \rho_{\mathrm{flipped}} = \frac{\langle g,\, \mathrm{flip}(r)\rangle}{\|g\|\,\|r\| + 10^{-12}}",
                    "note"  : "The spatial-mean unit-area elevation profiles of the GT and reduced cubes are mean-centred and correlated directly and against the reduced profile reversed in elevation; if the flipped correlation is larger the run logs a warning that the Capon elevation-sign convention (capon_phase_sign) should be verified on the server (reduced.py _report_orientation).",
                    "vars"  : [
                        {"sym": r"\rho_{\mathrm{aligned}}, \rho_{\mathrm{flipped}}", "desc": "correlation of GT and reduced mean profiles, aligned vs elevation-flipped"},
                        {"sym": r"g",                                                "desc": "mean-centred, unit-area, spatial-mean GT elevation profile"},
                        {"sym": r"r",                                                "desc": "same for the reduced-Capon cube"},
                        {"sym": r"\mathrm{flip}",                                    "desc": "elevation-axis reversal"},
                    ],
                },
                {
                    "title" : "Track coherence synthesis",
                    "tex"   : r"\gamma_{v,a,r} = \Delta x \sum_{n} p_{n,a,r}\,\exp\!\left(i\,k_{z,v,a,r}\,x_n\right)",
                    "note"  : "Interferometric coherence of an elevation profile at a track, projecting the profile onto the track's kz phase ramp; kz is the per-pixel geometry field sliced to the split region and secondary subset, with the height-axis convention read from the training run's docs/trainer_config.json (data_consistency.py _load_kz, PhysicalLoss.synthesise_track).",
                    "vars"  : [
                        {"sym": r"\gamma_{v,a,r}", "desc": "complex coherence synthesised at track v, pixel (a, r)"},
                        {"sym": r"k_{z,v,a,r}",    "desc": "per-pixel elevation wavenumber (kz) of track v"},
                        {"sym": r"x_n",            "desc": "elevation-axis sample"},
                        {"sym": r"p",              "desc": "elevation profile (predicted or GT)"},
                        {"sym": r"\Delta x",       "desc": "elevation-axis step"},
                    ],
                },
                {
                    "title" : "Interferometric coherence-resynthesis error map",
                    "tex"   : r"E^{\mathrm{coh}}_{a,r} = \frac{1}{V}\sum_{v=1}^{V}\left|\frac{\gamma^{\mathrm{pred}}_{v}}{\hat{p}_0} - \frac{\gamma^{\mathrm{GT}}_{v}}{p_0}\right|^2, \qquad m_{a,r} = \mathbb{1}\!\left[\textstyle\sum_n Y_{n,a,r}\,\Delta x > \phi\right]",
                    "note"  : "Per-pixel mean over tracks of the squared difference between the power-normalised predicted and GT coherences; a pixel is valid only where the GT total power exceeds physics_floor (1e-3), and the normalising powers are floored at the same value. The map is accumulated track by track inside DataConsistency._evaluate_chunks, which calls PhysicalLoss.synthesise_track once per track and divides the summed squared error by the track count, then reduced to masked mean/median/p95 plus a per-track error breakdown and saved when cubes are kept (pipelines/backbone/inference/data_consistency.py).",
                    "vars"  : [
                        {"sym": r"E^{\mathrm{coh}}_{a,r}",                               "desc": "per-pixel coherence-resynthesis error"},
                        {"sym": r"V",                                                    "desc": "number of tracks (primary + secondaries)"},
                        {"sym": r"\gamma^{\mathrm{pred}}_{v}, \gamma^{\mathrm{GT}}_{v}", "desc": "synthesised coherences of prediction and GT at track v"},
                        {"sym": r"\hat{p}_0, p_0",                                       "desc": r"predicted and GT total power (\sum_n Y \Delta x, floored at \phi)"},
                        {"sym": r"\phi",                                                 "desc": "physics_floor = 1e-3"},
                        {"sym": r"m_{a,r}",                                              "desc": "validity mask"},
                    ],
                },
                {
                    "title" : "Covariance-matching error map",
                    "tex"   : r"E^{\mathrm{cov}}_{a,r} = \frac{\sum_{i\le j} w_{ij}\,\bigl|\gamma^{\Delta}_{ij}\bigr|^2}{\max\!\left(\sum_{i\le j} w_{ij}\,\bigl|\gamma^{\mathrm{GT}}_{ij}\bigr|^2,\ 10^{-12}\right)}, \qquad w_{ij} = \begin{cases} 1 & i = j \\ 2 & i < j \end{cases}",
                    "note"  : "Per-pixel relative covariance error over all ordered track pairs i<=j; the prediction-minus-GT difference is synthesised once at each pair wavenumber (the covariance is linear in the profile), off-diagonal pairs are weighted double, and the denominator is the GT covariance energy floored at 1e-12; reduced to masked mean/median/p95 on the same GT-power mask (data_consistency.py, PhysicalLoss.covariance_matching_pp_map).",
                    "vars"  : [
                        {"sym": r"E^{\mathrm{cov}}_{a,r}",    "desc": "per-pixel covariance-matching error"},
                        {"sym": r"\gamma^{\Delta}_{ij}",      "desc": "synthesis of the prediction-minus-GT profile at wavenumber k_{z,i} - k_{z,j}"},
                        {"sym": r"\gamma^{\mathrm{GT}}_{ij}", "desc": "GT synthesis at the same track pair"},
                        {"sym": r"w_{ij}",                    "desc": "pair weight; off-diagonal pairs count double"},
                    ],
                },
                {
                    "title" : "Phase agreement and Capon-sign diagnosis",
                    "tex"   : r"r^{\mathrm{al}}_{v,s} = \frac{1}{N_v}\left|\sum_{(a,r)\in\Omega_v} m_{v,a,r}\,\overline{\hat{\gamma}^{\,s}_{v,a,r}}\right|, \qquad r^{\mathrm{fl}}_{v,s} = \frac{1}{N_v}\left|\sum_{(a,r)\in\Omega_v} m_{v,a,r}\,\hat{\gamma}^{\,s}_{v,a,r}\right|",
                    "note"  : "Mean resultant length between the measured interferogram unit phasor and the unit coherence synthesised from the GT (and prediction) profiles, per secondary track and averaged; the flipped variant drops the conjugate. When the GT flipped-agreement mean beats the aligned one, the run logs that the Capon elevation-sign convention (capon_phase_sign) is likely inverted for the stack. Measured phasors are optionally box-multilooked (phase_multilook = 9) before unit-normalisation (data_consistency.py).",
                    "vars"  : [
                        {"sym": r"r^{\mathrm{al}}_{v,s}, r^{\mathrm{fl}}_{v,s}", "desc": "aligned and flipped phase-agreement resultant length, track v, source s (GT or pred)"},
                        {"sym": r"m_{v,a,r}",                                    "desc": "measured unit interferogram phasor of secondary track v"},
                        {"sym": r"\hat{\gamma}^{\,s}_{v,a,r}",                   "desc": "unit-normalised coherence synthesised from the source-s profile"},
                        {"sym": r"\Omega_v, N_v",                                "desc": "valid pixels (GT-power mask and non-zero measurement) and their count"},
                    ],
                },
            ],
        }

    def _tuning(self) -> dict:
        """Returns the tuning group: the Optuna objective, TPE sampling, pruning and multi-GPU fan-out."""
        return {
            "group" : "Tuning",
            "blurb" : "Optuna hyperparameter search wrapped around the training pipeline: a single joint study with constant-liar TPE sampling and median pruning, fanned out across one worker per GPU and topped up in chunks until the trial target is reached.",
            "items" : [
                {
                    "title" : "Search objective",
                    "tex"   : r"f(\theta) = \min_{e \in \{1,\dots,E\}} \mathcal{L}^{(e)}_{\mathrm{val}}(\theta)",
                    "note"  : "Each trial trains a full model up to the epoch budget and returns the best validation loss over the epochs it actually runs; within-trial early stopping (patience p) halts a stalled trial before the budget is spent. The multivariate TPE sampler proposes with constant-liar parallelism across GPU workers.",
                    "vars"  : [
                        {"sym": r"f(\theta)",                        "desc": "objective value minimised by the study"},
                        {"sym": r"\theta",                           "desc": "sampled hyperparameter vector"},
                        {"sym": r"e",                                "desc": "epoch index within the trial"},
                        {"sym": r"E",                                "desc": "epoch budget per trial, n_epochs = 30"},
                        {"sym": r"\mathcal{L}^{(e)}_{\mathrm{val}}", "desc": "validation loss at epoch e"},
                        {"sym": r"p",                                "desc": "within-trial early-stop patience, early_stop_patience = 8"},
                    ],
                },
                {
                    "title" : "Joint search with chunked resume",
                    "tex"   : r"\theta^* = \operatorname*{arg\,min}_{\theta \in \Theta_{\mathrm{lr}} \times \Theta_{\mathrm{arch}}} f(\theta), \qquad n_{\mathrm{run}} = \max\!\left(0,\ N - \left|\mathcal{T}_{\mathrm{done}}\right|\right)",
                    "note"  : "Learning, regularisation and architecture parameters are sampled jointly in a single study; the SQLite-backed study is topped up across runs until the trial target is reached, and the best configuration so far is rewritten after every completed trial.",
                    "vars"  : [
                        {"sym": r"\theta^*",                    "desc": "best joint hyperparameter vector found so far"},
                        {"sym": r"\Theta_{\mathrm{lr}}",        "desc": "per-group rates and decays (log-uniform), dropout"},
                        {"sym": r"\Theta_{\mathrm{arch}}",      "desc": "widths, bottleneck, activation, normalisation, upsampling"},
                        {"sym": r"N",                           "desc": "trial target for the study, n_trials"},
                        {"sym": r"\mathcal{T}_{\mathrm{done}}", "desc": "completed and pruned trials already in storage"},
                        {"sym": r"n_{\mathrm{run}}",            "desc": "trials launched by the current chunk"},
                    ],
                },
                {
                    "title" : "Constant-liar worker fan-out",
                    "tex"   : r"n_i = \left\lfloor n_{\mathrm{run}} / W \right\rfloor + \mathbb{1}\!\left[\,i < (n_{\mathrm{run}} \bmod W)\,\right], \qquad i = 0,\dots,W-1",
                    "note"  : "The chunk's remaining trials are spread as evenly as possible over one worker process per GPU; every worker opens the same SQLite-backed study and draws from a TPE sampler seeded by base_seed + gpu_id, so constant-liar bookkeeping keeps the parallel in-flight trials from colliding. Workers assigned zero trials are skipped, and any trial left RUNNING by an interrupted chunk is marked failed before new workers launch.",
                    "vars"  : [
                        {"sym": r"n_i",              "desc": "trials assigned to worker (GPU) i"},
                        {"sym": r"n_{\mathrm{run}}", "desc": "remaining trials in the current chunk"},
                        {"sym": r"W",                "desc": "number of GPU workers, len(gpus)"},
                        {"sym": r"i",                "desc": "worker / GPU index"},
                    ],
                },
                {
                    "title" : "Median pruning rule",
                    "tex"   : r"\text{prune at epoch } t \iff \mathcal{L}^{(t)}_{\mathrm{val}} > \operatorname{median}\!\left\{\mathcal{L}^{(t)}_{\mathrm{val}}\ \text{of completed trials}\right\}",
                    "note"  : "Each epoch the trial reports its validation loss and is pruned once it exceeds the running median of previously completed trials at the same epoch; pruning stays inactive until n_startup trials have completed and until the trial is at least n_warmup epochs in. A pruned trial still counts toward the target alongside completed ones, whereas a trial that raises a non-prune exception is marked FAIL, propagates out of the worker, and is excluded from the target so the study keeps launching to replace it.",
                    "vars"  : [
                        {"sym": r"\mathcal{L}^{(t)}_{\mathrm{val}}", "desc": "trial's validation loss reported at epoch t"},
                        {"sym": r"t",                                "desc": "epoch index within the trial"},
                        {"sym": r"n_{\mathrm{startup}}",             "desc": "pruner_n_startup_trials = 8"},
                        {"sym": r"n_{\mathrm{warmup}}",              "desc": "pruner_n_warmup_steps = 8"},
                    ],
                },
            ],
        }

    def _learned_inversion(self) -> dict:
        """Returns the learned-inversion group: the unrolled gamma_net iteration and the gated set-prediction head."""
        return {
            "group" : "Learned Inversion",
            "blurb" : "The unrolled physics network (gamma_net) that inverts the forward model directly, and the gated set-prediction head that makes slot existence explicit.",
            "items" : [
                {
                    "title" : "Matched-filter initialisation",
                    "tex"   : r"\mathbf{s}^{0} = \max\!\Big(0,\ \tfrac{1}{T}\,\mathrm{Re}\!\left[\mathbf{A}^{\!H}\mathbf{y}\right]\Big)",
                    "note"  : "The unrolled network starts from the beamforming solution: the adjoint of the per-pixel steering operator applied to the coherence measurements, averaged over tracks and clipped to nonnegative reflectivity (GammaNet.forward, TomoOperator.adjoint).",
                    "vars"  : [
                        {"sym": r"\mathbf{s}^{0}", "desc": "initial reflectivity profile on the elevation grid (length N)"},
                        {"sym": r"\mathbf{y}",     "desc": "complex coherence measurements over the T tracks (per pixel)"},
                        {"sym": r"\mathbf{A}",     "desc": "per-pixel steering operator, A_tn = exp(j kz_t z_n) dz, built from the geometry-field kz map"},
                        {"sym": r"T",              "desc": "number of tracks"},
                    ],
                },
                {
                    "title" : "Unrolled proximal-gradient iteration",
                    "tex"   : r"\mathbf{r}^{l} = \mathbf{s}^{l} + \alpha_l\,\frac{\mathrm{Re}\!\left[\mathbf{A}^{\!H}(\mathbf{y} - \mathbf{A}\mathbf{s}^{l})\right]}{L_{\mathrm{lip}}}, \qquad \mathbf{s}^{l+1} = \max\!\big(0,\ \mathcal{P}_l(\mathbf{r}^{l}) - \theta_l\big)",
                    "note"  : "One layer of gamma_net: a gradient step on the data-fidelity term with a learned step size, a learned per-pixel 1D convolutional prox along the elevation axis, and a nonnegative soft-threshold with a learned threshold. Steps and thresholds are softplus-reparameterised so they stay positive; each of the L layers has its own alpha_l, theta_l and prox (GammaNet.forward, ProfileProx).",
                    "vars"  : [
                        {"sym": r"\mathbf{s}^{l}",   "desc": "profile estimate after layer l"},
                        {"sym": r"\alpha_l",         "desc": "learned step size of layer l (softplus of a raw parameter)"},
                        {"sym": r"\theta_l",         "desc": "learned soft-threshold of layer l"},
                        {"sym": r"\mathcal{P}_l",    "desc": "learned prox of layer l: residual half-resolution bottleneck along elevation (strided window GEMM -> act -> Conv1d, linearly upsampled)"},
                        {"sym": r"L_{\mathrm{lip}}", "desc": "Lipschitz normaliser of the gradient (next card)"},
                    ],
                },
                {
                    "title" : "Lipschitz-normalised gradient step",
                    "tex"   : r"L_{\mathrm{lip}} = T\,N\,\mathrm{d}z^{2}",
                    "note"  : "Bound on the spectral norm of A^H A used to normalise the gradient so step_init = 1.0 is stable for any track count, grid length or grid spacing. Without this normalisation the iteration diverges: the raw operator norm is of order T*N*dz^2 (about 230 for the default layout), far beyond a unit step.",
                    "vars"  : [
                        {"sym": r"T",           "desc": "number of tracks"},
                        {"sym": r"N",           "desc": "number of elevation grid points"},
                        {"sym": r"\mathrm{d}z", "desc": "elevation grid spacing (m)"},
                    ],
                },
                {
                    "title" : "Set-prediction amplitude gate",
                    "tex"   : r"g_k = \sigma(\ell_k), \qquad \hat{a}_k = g_k\,a_k + (1 - g_k)\,o_k",
                    "note"  : "The gated set-prediction head (head = set_pred, selectable on every backbone): an existence-logit PixelMLP emits one logit per Gaussian slot, and its sigmoid blends the regressed amplitude toward a learned per-slot off level. The off level lives in normalised output space because normalised zero is not physical zero; training drives o_k toward the normalised encoding of physical amplitude zero. Pairs with hungarian param matching; mu and sigma pass through ungated (OutputHeadsMixin._set_prediction_forward).",
                    "vars"  : [
                        {"sym": r"\ell_k",    "desc": "existence logit of slot k (per pixel)"},
                        {"sym": r"g_k",       "desc": "sigmoid existence gate in [0, 1]"},
                        {"sym": r"a_k",       "desc": "raw regressed amplitude of slot k (normalised space)"},
                        {"sym": r"o_k",       "desc": "learned scalar off level of slot k, initialised at 0"},
                        {"sym": r"\hat{a}_k", "desc": "gated amplitude emitted in the 3K-channel output"},
                    ],
                },
            ],
        }

    def collect(self) -> list[dict]:
        """Returns every equation group in presentation order."""
        return [
            self._signal_model(),
            self._processing(),
            self._param_extraction(),
            self._dataset(),
            self._training_loss(),
            self._training_optim(),
            self._learned_inversion(),
            self._inference(),
            self._tuning(),
        ]
