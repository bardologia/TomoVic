"""Curated flow diagrams describing each TomoSAR pipeline for the web UI.

Every private builder returns one flow definition: a key, a display name, a
prose blurb, the list of symbol nodes (tensors, matrices, scalars and sets with
their shapes, roles and sample values) and the ordered processing steps that
consume and produce them. The web UI renders these as animated MathJax flows.
"""


class FlowLibrary:
    """Builds the animated flow definitions served to the web UI."""

    def _processing(self) -> dict:
        """Returns the flow for SLC preprocessing into interferograms and tomograms."""
        nodes = [
            {"id": "passes", "tex": r"\mathbf{s}",            "role": "measured",     "kind": "tensor", "shape": "N_p x A_z x R_g", "desc": "co-registered SLC pass stack loaded internally by PyRat FuSARtomo",      "sample": [["0.8+0.2j", "0.6-0.4j"], ["0.5+0.5j", "0.9-0.1j"]]},
            {"id": "s0",     "tex": r"s_0",                   "role": "measured",     "kind": "matrix", "shape": "A_z x R_g",       "desc": "master (primary) SLC, complex (PyRat RGI-SLC)",                          "sample": [["0.8+0.2j", "0.6-0.4j", "1.1+0.0j"], ["0.5+0.5j", "0.9-0.1j", "0.7+0.3j"], ["1.0+0.2j", "0.4-0.6j", "0.8+0.1j"]]},
            {"id": "si",     "tex": r"s_i",                   "role": "measured",     "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "co-registered secondary SLC stack (PyRat INF-SLC)",                      "sample": [["0.7+0.3j", "0.5-0.3j"], ["0.6+0.4j", "0.8-0.2j"]]},
            {"id": "phidem", "tex": r"\phi_{\mathrm{DEM},i}", "role": "measured",     "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "DEM-predicted phase per pass (rad)",                                     "sample": [["0.12", "0.31"], ["0.27", "0.44"]]},
            {"id": "trk",    "tex": r"\mathbf{t}_i",          "role": "measured",     "kind": "tensor", "shape": "N_p x R x A_z",   "desc": "per-pass INF-TRACK position file; row 2 horizontal, row 3 vertical",     "sample": [["...h...", "...v..."]]},
            {"id": "par",    "tex": r"\rho_i",                "role": "measured",     "kind": "set",    "shape": "N_p",             "desc": "per-pass acquisition params: r, lambda, h0, terrain, antdir (pp_*.xml)", "sample": "lambda, r, h0, terrain, antdir"},
            {"id": "M",      "tex": r"M",                     "role": "calculated",   "kind": "scalar", "shape": "1",               "desc": "number of azimuth subsections",                                          "sample": "15"},
            {"id": "PT",     "tex": r"(P,T)",                 "role": "calculated",   "kind": "scalar", "shape": "1",               "desc": "resolved (workers, threads-per-worker) plan",                            "sample": "(8, 2)"},
            {"id": "Rhat",   "tex": r"\hat{\mathbf{R}}",      "role": "intermediate", "kind": "matrix", "shape": "N_p x N_p",       "desc": "Boxcar-windowed per-pixel sample covariance (PyRat-internal)",           "sample": [["1.0", "0.7"], ["0.7", "1.0"]]},
            {"id": "Tm",     "tex": r"T_m",                   "role": "calculated",   "kind": "tensor", "shape": "H x W_m x R_g",   "desc": "Capon beamformed tomogram of subsection m",                              "sample": [["0.2", "0.9", "0.3"], ["0.1", "0.7", "0.8"], ["0.0", "0.4", "1.0"]]},
            {"id": "DEMm",   "tex": r"D_m",                   "role": "calculated",   "kind": "matrix", "shape": "W_m x R_g",       "desc": "DEM of subsection m (PyRat byproduct)",                                  "sample": [["31.2", "30.8"], ["32.1", "31.5"]]},
            {"id": "Tcomb",  "tex": r"T_{\mathrm{comb}}",     "role": "final",        "kind": "tensor", "shape": "H x A_z x R_g",   "desc": "combined beamformed tomogram, model reconstruction reference",           "sample": [["0.2", "0.9", "0.3"], ["0.1", "0.7", "0.8"], ["0.0", "0.4", "1.0"]]},
            {"id": "DEM",    "tex": r"D",                     "role": "final",        "kind": "matrix", "shape": "A_z x R_g",       "desc": "full-stack concatenated DEM (m)",                                        "sample": [["31.2", "30.8"], ["32.1", "31.5"]]},
            {"id": "stilde", "tex": r"\tilde{s}_i",           "role": "intermediate", "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "DEM-deramped secondary SLC",                                             "sample": [["0.6+0.1j", "0.5-0.1j"], ["0.7+0.2j", "0.6-0.0j"]]},
            {"id": "cross",  "tex": r"c_i",                   "role": "intermediate", "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "raw master-secondary cross-product",                                     "sample": [["0.45+0.30j", "0.41-0.12j"], ["0.55+0.18j", "0.48-0.05j"]]},
            {"id": "pi",     "tex": r"p_i",                   "role": "intermediate", "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "unit-magnitude interferometric phasor",                                  "sample": [["0.83+0.55j", "0.96-0.28j"], ["0.95+0.31j", "0.99-0.10j"]]},
            {"id": "Ai",     "tex": r"A_i",                   "role": "intermediate", "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "clipped secondary amplitude weight",                                     "sample": [["0.71", "0.93"], ["1.25", "0.58"]]},
            {"id": "phii",   "tex": r"\tilde{\phi}_i",        "role": "final",        "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "amplitude-weighted complex interferogram (network input)",               "sample": [["0.51+0.20j", "0.44-0.12j"], ["0.63+0.18j", "0.55-0.05j"]]},
            {"id": "bv",     "tex": r"b^{\mathrm{v}}_i",      "role": "calculated",   "kind": "vector", "shape": "N_p",             "desc": "vertical baseline relative to reference pass (m)",                       "sample": ["0.00", "12.4", "-8.1", "20.7"]},
            {"id": "bh",     "tex": r"b^{\mathrm{h}}_i",      "role": "calculated",   "kind": "vector", "shape": "N_p",             "desc": "horizontal baseline relative to reference pass (m)",                     "sample": ["0.00", "5.2", "-3.4", "9.8"]},
            {"id": "prof",   "tex": r"\mathbf{\tau}_i",       "role": "calculated",   "kind": "tensor", "shape": "N_p x A_z",       "desc": "per-azimuth horizontal/vertical track position profiles (m)",            "sample": [["112.3", "112.5"], ["101.7", "101.9"]]},
            {"id": "look",   "tex": r"\theta",                "role": "calculated",   "kind": "vector", "shape": "R_g",             "desc": "per-range look angle theta (rad)",                                       "sample": ["0.79", "0.80", "...", "1.02"]},
            {"id": "brel",   "tex": r"\mathbf{\beta}_i",      "role": "calculated",   "kind": "tensor", "shape": "N_p x A_z",       "desc": "reference-relative baseline profiles, horizontal & vertical (m)",        "sample": [["0.00", "0.00"], ["5.2", "4.9"]]},
            {"id": "geom",   "tex": r"k_z",                   "role": "final",        "kind": "tensor", "shape": "N_p x A_z x R_g", "desc": "per-pixel interferometric wavenumber k_z (rad/m) for the physics loss",  "sample": [["0.00", "0.00"], ["0.11", "0.12"]]},
        ]
        steps = [
            {
                "id": "subdivide", "title": "Azimuth subdivision and worker plan", "phase": "A - Tomogram (Capon)",
                "note": "When the crop azimuth exceeds max_crop_azimuth_width (1000 lines) it is split into M contiguous, non-overlapping subsections; the (workers, threads) plan minimises the number of dispatch waves within a core budget B = floor(0.8 x cores) at the default 'high' effort, with threads per worker capped at 16.",
                "inputs": [], "outputs": ["M", "PT"],
                "lines": [
                    [{"id": "M", "tex": r"M", "role": "calculated"}, {"tex": "="}, {"tex": r"\left\lceil W_{\mathrm{az}} / W_{\max} \right\rceil,\qquad W_{\max} = 1000"}],
                    [{"id": "PT", "tex": r"(P,T)", "role": "calculated"}, {"tex": "="}, {"tex": r"\arg\min_{P \le B}\left\lceil M/P \right\rceil,\quad T = \min(16,\ \lfloor B/P \rfloor),\quad B = \lfloor 0.8\,C \rfloor"}],
                ],
            },
            {
                "id": "covariance", "title": "Boxcar sample covariance", "phase": "A - Tomogram (Capon)",
                "note": "Each subsection is beamformed by an independent PyRat FuSARtomo worker; the Boxcar filter with win = [20, 10] averages the co-registered SLC pass stack over a 20x10-pixel window to estimate the per-pixel sample covariance. The averaging is internal to PyRat, this stage only sets the filter and its window.",
                "inputs": ["passes"], "outputs": ["Rhat"],
                "lines": [
                    [{"id": "Rhat", "tex": r"\hat{\mathbf{R}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\big\langle\,"}, {"id": "passes", "tex": r"\mathbf{s}\,\mathbf{s}^{H}", "role": "measured"}, {"tex": r"\,\big\rangle_{W_{\mathrm{box}}},\qquad W_{\mathrm{box}} = 20 \times 10"}],
                ],
            },
            {
                "id": "capon", "title": "Capon beamforming over elevation", "phase": "A - Tomogram (Capon)",
                "note": "FuSARtomo runs the Capon (MVDR) minimum-variance estimator over the configured height range [-20, 80] m and writes each subsection's tomogram and DEM to HDF5; the steering vector a(xi) is PyRat's internal geometry model, not computed by this stage.",
                "inputs": ["Rhat"], "outputs": ["DEMm", "Tm"],
                "lines": [
                    [{"id": "Tm", "tex": r"T_m(\xi)", "role": "calculated"}, {"tex": r"\;\propto\;"}, {"tex": r"\dfrac{1}{\mathbf{a}^{H}(\xi)\,"}, {"id": "Rhat", "tex": r"\hat{\mathbf{R}}^{-1}", "role": "intermediate"}, {"tex": r"\,\mathbf{a}(\xi)},\qquad \xi \in [-20,\ 80]\,\mathrm{m}"}],
                ],
            },
            {
                "id": "concat", "title": "Subsection concatenation", "phase": "A - Tomogram (Capon)",
                "note": "The worker HDF5 files are reassembled along azimuth into the full-stack products: the 2-D DEM concatenates on axis 0 and the 3-D tomogram on axis 1, then both are saved as .npy. The combined tomogram is the model's reconstruction reference.",
                "inputs": ["Tm", "DEMm"], "outputs": ["DEM", "Tcomb"],
                "lines": [
                    [{"id": "DEM", "tex": r"D", "role": "final"}, {"tex": "="}, {"tex": r"\mathrm{concat}\!\left[\,"}, {"id": "DEMm", "tex": r"D_0, \dots, D_{M-1}", "role": "calculated"}, {"tex": r"\,\right]_{\mathrm{axis}=0}"}],
                    [{"id": "Tcomb", "tex": r"T_{\mathrm{comb}}", "role": "final"}, {"tex": "="}, {"tex": r"\mathrm{concat}\!\left[\,"}, {"id": "Tm", "tex": r"T_0, \dots, T_{M-1}", "role": "calculated"}, {"tex": r"\,\right]_{\mathrm{axis}=1}"}],
                ],
            },
            {
                "id": "slc_load", "title": "SLC loading and co-registration", "phase": "B - Interferograms",
                "note": "The master is read as the geocoded range-Doppler SLC (RGI-SLC); each secondary is the interferometric SLC already co-registered to the master (INF-SLC), loaded together with its DEM-predicted phase (phadem).",
                "inputs": [], "outputs": ["s0", "si", "phidem"],
                "lines": [
                    [{"id": "s0", "tex": r"s_0", "role": "measured"}, {"tex": "="}, {"tex": r"\mathrm{load}\big(\mathrm{master};\ \mathtt{RGI\text{-}SLC}\big)"}],
                    [{"id": "si", "tex": r"s_i", "role": "measured"}, {"tex": "="}, {"tex": r"\mathrm{load}\big(\mathrm{sec}_i;\ \mathtt{INF\text{-}SLC}\big),\quad"}, {"id": "phidem", "tex": r"\phi_{\mathrm{DEM},i}", "role": "measured"}, {"tex": r"= \mathrm{phadem}_i"}],
                ],
            },
            {
                "id": "baselines", "title": "Track baseline extraction", "phase": "B - Interferograms",
                "note": "Per pass, the horizontal (row 2) and vertical (row 3) track positions are read from the INF-TRACK file over the crop azimuth window; the scalar baselines are their azimuth means referenced to the reference pass, and the full per-azimuth profiles are kept to build the geometry field.",
                "inputs": ["trk"], "outputs": ["bv", "bh", "prof"],
                "lines": [
                    [{"id": "bv", "tex": r"b^{\mathrm{v}}_i", "role": "calculated"}, {"tex": "="}, {"tex": r"\overline{\tau^{\mathrm{v}}_i} - \overline{\tau^{\mathrm{v}}_0},\qquad"}, {"id": "bh", "tex": r"b^{\mathrm{h}}_i", "role": "calculated"}, {"tex": "="}, {"tex": r"\overline{\tau^{\mathrm{h}}_i} - \overline{\tau^{\mathrm{h}}_0}"}],
                    [{"id": "prof", "tex": r"\mathbf{\tau}_i", "role": "calculated"}, {"tex": "="}, {"id": "trk", "tex": r"\mathbf{t}_i", "role": "measured"}, {"tex": r"[\,2{:}4,\ \mathtt{az}_0{:}\mathtt{az}_1\,]\quad (\text{h, v rows})"}],
                ],
            },
            {
                "id": "deramp", "title": "DEM-phase deramping", "phase": "B - Interferograms",
                "note": "Each secondary is multiplied by the DEM phasor; after the later conjugation this subtracts the DEM-predicted phase, removing terrain topography and leaving sub-resolution elevation structure.",
                "inputs": ["si", "phidem"], "outputs": ["stilde"],
                "lines": [
                    [{"id": "stilde", "tex": r"\tilde{s}_i", "role": "intermediate"}, {"tex": "="}, {"id": "si", "tex": r"s_i", "role": "measured"}, {"tex": r"\cdot"}, {"tex": r"\exp\!\left(j\,"}, {"id": "phidem", "tex": r"\phi_{\mathrm{DEM},i}", "role": "measured"}, {"tex": r"\right)"}],
                ],
            },
            {
                "id": "crossprod", "title": "Master-secondary cross-product", "phase": "B - Interferograms",
                "note": "Conjugating the deramped secondary against the master leaves the phase difference minus the DEM phase; the conjugation flips the DEM sign, so it is effectively subtracted.",
                "inputs": ["s0", "stilde"], "outputs": ["cross"],
                "lines": [
                    [{"id": "cross", "tex": r"c_i", "role": "intermediate"}, {"tex": "="}, {"id": "s0", "tex": r"s_0", "role": "measured"}, {"tex": r"\cdot"}, {"id": "stilde", "tex": r"\overline{\tilde{s}_i}", "role": "intermediate"}],
                    [{"tex": r"\arg(c_i)"}, {"tex": "="}, {"tex": r"\psi_0 - \psi_i - \phi_{\mathrm{DEM},i}"}],
                ],
            },
            {
                "id": "phasor", "title": "Unit-phasor normalisation", "phase": "B - Interferograms",
                "note": "Dividing by the cross-product magnitude (floored at 1e-30) removes inter-pass amplitude differences while preserving coherence; null pixels collapse to zero instead of NaN.",
                "inputs": ["cross"], "outputs": ["pi"],
                "lines": [
                    [{"id": "pi", "tex": r"p_i", "role": "intermediate"}, {"tex": "="}, {"tex": r"\dfrac{"}, {"id": "cross", "tex": r"c_i", "role": "intermediate"}, {"tex": r"}{\left|c_i\right| + \epsilon},\qquad \epsilon = 10^{-30}"}],
                ],
            },
            {
                "id": "clip", "title": "Amplitude clipping", "phase": "B - Interferograms",
                "note": "The secondary amplitude is clipped at max_amplitude_clip = 1.25 so bright corner reflectors or artefacts cannot dominate the per-pass weight.",
                "inputs": ["si"], "outputs": ["Ai"],
                "lines": [
                    [{"id": "Ai", "tex": r"A_i", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{clip}\!\big(\big|"}, {"id": "si", "tex": r"s_i", "role": "measured"}, {"tex": r"\big|,\ 0,\ c_{\max}\big),\qquad c_{\max} = 1.25"}],
                ],
            },
            {
                "id": "interf", "title": "Amplitude-weighted interferogram", "phase": "B - Interferograms",
                "note": "Re-attaching the clipped amplitude as the phasor's modulus gives an interferogram whose phase is the residual (sub-DEM) elevation phase and whose magnitude is a bounded signal-strength proxy; this stack is the network input.",
                "inputs": ["Ai", "pi"], "outputs": ["phii"],
                "lines": [
                    [{"id": "phii", "tex": r"\tilde{\phi}_i", "role": "final"}, {"tex": "="}, {"id": "Ai", "tex": r"A_i", "role": "intermediate"}, {"tex": r"\cdot"}, {"id": "pi", "tex": r"p_i", "role": "intermediate"}, {"tex": "="}, {"id": "Ai", "tex": r"A_i", "role": "intermediate"}, {"tex": r"\dfrac{s_0\,\overline{\tilde{s}_i}}{\left|s_0\,\overline{\tilde{s}_i}\right| + \epsilon}"}],
                ],
            },
            {
                "id": "trackgeo", "title": "Look angle and relative baselines", "phase": "C - Geometry field",
                "note": "The look angle is recovered per range bin from the reference-pass geometry, arccos of sensor-height-above-terrain over slant range; the build aborts when that height is non-positive or reaches the nearest slant range, because clamping the ratio into [-1, 1] would otherwise silently yield a zero look angle and an infinite kz. The per-azimuth position profiles become baselines relative to the reference pass. A left-looking stack (antdir <= 0) aborts, since the kz formula assumes a right-looking geometry.",
                "inputs": ["par", "prof"], "outputs": ["look", "brel"],
                "lines": [
                    [{"id": "look", "tex": r"\theta(r)", "role": "calculated"}, {"tex": "="}, {"tex": r"\arccos\!\Big(\mathrm{clip}\big(\tfrac{h_0 - \mathrm{terrain}}{r},\,-1,\,1\big)\Big),\quad r = "}, {"id": "par", "tex": r"\rho_0.r", "role": "measured"}, {"tex": r"[\mathtt{rg}_0{:}\mathtt{rg}_1]"}],
                    [{"id": "brel", "tex": r"\mathbf{\beta}_i", "role": "calculated"}, {"tex": "="}, {"id": "prof", "tex": r"\mathbf{\tau}_i", "role": "calculated"}, {"tex": r"-\ "}, {"id": "prof", "tex": r"\mathbf{\tau}_0", "role": "calculated"}, {"tex": r"\qquad (\text{rel. to reference pass})"}],
                ],
            },
            {
                "id": "geomfield", "title": "Per-pixel wavenumber field", "phase": "C - Geometry field",
                "note": "The perpendicular baseline projects the horizontal and vertical baselines onto the look direction, and the interferometric wavenumber (default height convention, dividing by r sin theta) is stored per (pass, azimuth, range) as the geometry field consumed by the physics loss; the reference pass has zero baseline, so its kz vanishes.",
                "inputs": ["look", "brel", "par"], "outputs": ["geom"],
                "lines": [
                    [{"tex": r"b^{\perp}_i"}, {"tex": "="}, {"id": "brel", "tex": r"b^{\mathrm{h}}_i", "role": "calculated"}, {"tex": r"\cos"}, {"id": "look", "tex": r"\theta", "role": "calculated"}, {"tex": r"+\ "}, {"id": "brel", "tex": r"b^{\mathrm{v}}_i", "role": "calculated"}, {"tex": r"\sin"}, {"id": "look", "tex": r"\theta", "role": "calculated"}],
                    [{"id": "geom", "tex": r"k_{z,i}", "role": "final"}, {"tex": "="}, {"tex": r"\dfrac{4\pi}{\lambda}\,\dfrac{b^{\perp}_i}{r\,\sin\theta}\qquad (\text{height convention})"}],
                ],
            },
        ]
        return {
            "key"   : "processing",
            "name"  : "Processing (Tomogram + Interferograms)",
            "blurb" : "From the F-SAR SLC passes to the model's reference tomogram and input interferograms. Each azimuth subsection is Capon-beamformed by a PyRat FuSARtomo worker and reassembled; the co-registered secondaries are DEM-deramped and amplitude-weighted into the interferometric stack; and the track geometry becomes a per-pixel wavenumber field for the physics loss.",
            "nodes" : nodes,
            "steps" : steps,
        }

    def _param_extraction(self) -> dict:
        """Returns the flow for per-pixel K-Gaussian fitting of elevation profiles."""
        nodes = [
            {"id": "T",       "tex": r"T",                         "role": "measured",     "kind": "tensor", "shape": "H x Az x R", "desc": "beamformed tomogram from processing, magnitude taken per profile", "sample": [["0.2", "0.9", "0.3"], ["0.1", "0.7", "0.8"], ["0.0", "0.4", "1.0"]]},
            {"id": "P",       "tex": r"P_h",                       "role": "intermediate", "kind": "vector", "shape": "H",          "desc": "thresholded and truncated magnitude profile over elevation",       "sample": ["0.00", "0.62", "0.31", "0.88", "0.00"]},
            {"id": "active",  "tex": r"\mathbb{1}_{\mathrm{act}}", "role": "intermediate", "kind": "scalar", "shape": "1",          "desc": "active-profile gate (profile max above tau_a)",                    "sample": "1"},
            {"id": "scale",   "tex": r"s",                         "role": "intermediate", "kind": "scalar", "shape": "1",          "desc": "per-profile scale = profile max (1 if inactive)",                  "sample": "0.88"},
            {"id": "gtilde",  "tex": r"\tilde{\gamma}_h",          "role": "intermediate", "kind": "vector", "shape": "H",          "desc": "peak-normalised profile (tallest bin equals one)",                 "sample": ["0.00", "0.70", "0.35", "1.00", "0.00"]},
            {"id": "peaks",   "tex": r"\mathcal{P}",               "role": "intermediate", "kind": "set",    "shape": "P",          "desc": "prominence-and-distance gated peak indices, prominence-sorted",    "sample": ["97", "34", "151"]},
            {"id": "sigbase", "tex": r"\sigma_{\mathrm{base}}",    "role": "intermediate", "kind": "scalar", "shape": "1",          "desc": "span-derived width scale, sets d_min and sig0, m",                 "sample": "2.50"},
            {"id": "sig0",    "tex": r"\sigma^{(0)}",              "role": "intermediate", "kind": "vector", "shape": "K",          "desc": "shared initial width guess, m",                                    "sample": ["0.62", "0.62", "0.62"]},
            {"id": "idxs",    "tex": r"\mathcal{I}",               "role": "intermediate", "kind": "set",    "shape": "K",          "desc": "K seed indices (peaks then residual-argmax fill)",                 "sample": ["97", "34", "151", "12", "180"]},
            {"id": "mu0",     "tex": r"\mu",                       "role": "intermediate", "kind": "vector", "shape": "K",          "desc": "seed component means at peak elevations, m",                       "sample": ["12.4", "31.8", "47.0"]},
            {"id": "a0",      "tex": r"a",                         "role": "intermediate", "kind": "vector", "shape": "K",          "desc": "seed component amplitudes at peaks, raw units",                    "sample": ["0.88", "0.62", "0.34"]},
            {"id": "loss",    "tex": r"\mathcal{L}",               "role": "intermediate", "kind": "scalar", "shape": "1",          "desc": "per-profile MSE on the normalised profile",                        "sample": "3.4e-2"},
            {"id": "grad",    "tex": r"g_t",                       "role": "intermediate", "kind": "vector", "shape": "K",          "desc": "loss gradient at step t, masked to free parameters",               "sample": ["-0.04", "0.01", "-0.02"]},
            {"id": "sigstar", "tex": r"\sigma^{*}",                "role": "calculated",   "kind": "vector", "shape": "K",          "desc": "fitted, clamped component widths, m",                              "sample": ["1.84", "2.55", "3.10"]},
            {"id": "mseK",    "tex": r"\mathrm{MSE}_K",            "role": "intermediate", "kind": "vector", "shape": "K_max",      "desc": "per-order residual MSE on the normalised profile",                 "sample": ["0.18", "0.04", "0.05", "0.07", "0.06"]},
            {"id": "penK",    "tex": r"\mathcal{L}_K",             "role": "intermediate", "kind": "vector", "shape": "K_max",      "desc": "penalised score per model order K",                                "sample": ["0.19", "0.06", "0.08", "0.11", "0.11"]},
            {"id": "Kstar",   "tex": r"K^{*}",                     "role": "calculated",   "kind": "scalar", "shape": "1",          "desc": "selected number of active components",                             "sample": "2"},
            {"id": "aout",    "tex": r"a^{\mathrm{out}}",          "role": "calculated",   "kind": "vector", "shape": "K",          "desc": "winner amplitudes rescaled to raw units",                          "sample": ["0.81", "0.55"]},
            {"id": "theta",   "tex": r"\theta",                    "role": "final",        "kind": "vector", "shape": "3K",         "desc": "mean-ordered interleaved (a, mu, sigma) supervised target",        "sample": ["a_1", "mu_1", "sig_1", "a_2", "..."]},
            {"id": "r2",      "tex": r"R^2",                       "role": "final",        "kind": "matrix", "shape": "Az x R",     "desc": "per-pixel fit-quality map",                                        "sample": [["0.97", "0.91"], ["0.88", "0.99"]]},
            {"id": "mrel",    "tex": r"m_{\mathrm{rel}}",          "role": "final",        "kind": "matrix", "shape": "Az x R",     "desc": "relative K-selection margin diagnostic",                           "sample": [["0.31", "0.04"], ["0.12", "0.55"]]},
        ]
        steps = [
            {
                "id": "threshold", "title": "Profile floor and truncation", "phase": "0 - Conditioning",
                "note": "The elevation profile is the tomogram magnitude; ProfilePreprocessor zeroes every sample not exceeding t_f = 0.25 of the per-profile max, then zeroes all bins from index H_tr = 170 onward. This is the exact conditioning the fit, R2 and contrast all consume.",
                "inputs": ["T"], "outputs": ["P"],
                "lines": [
                    [{"id": "P", "tex": r"P_h", "role": "intermediate"}, {"tex": "="}, {"id": "T", "tex": r"\left|T_h\right|", "role": "measured"}, {"tex": r"\cdot\,\mathbb{1}\!\left[\left|T_h\right| > t_f \max_h \left|T_h\right|\right],\quad t_f = 0.25"}],
                    [{"id": "P", "tex": r"P_h", "role": "intermediate"}, {"tex": r"\leftarrow 0\quad \text{for } h \ge H_{\mathrm{tr}} = 170"}],
                ],
            },
            {
                "id": "activity", "title": "Active-profile gate", "phase": "0 - Conditioning",
                "note": "A profile is fitted only if its maximum clears the activity threshold; inactive profiles are skipped (all parameters stay zero) and take scale 1 so normalisation is a no-op.",
                "inputs": ["P"], "outputs": ["active", "scale"],
                "lines": [
                    [{"id": "active", "tex": r"\mathbb{1}_{\mathrm{act}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathbb{1}\!\left[\max_h "}, {"id": "P", "tex": r"P_h", "role": "intermediate"}, {"tex": r" > \tau_a\right],\qquad \tau_a = 10^{-3}"}],
                    [{"id": "scale", "tex": r"s", "role": "intermediate"}, {"tex": "="}, {"tex": r"\max_h "}, {"id": "P", "tex": r"P_h", "role": "intermediate"}, {"tex": r"\ \ (\text{active}),\qquad 1\ \ (\text{else})"}],
                ],
            },
            {
                "id": "pnorm", "title": "Peak normalisation", "phase": "0 - Conditioning",
                "note": "Dividing by the per-profile maximum sets the tallest peak to one, decoupling the fit loss from absolute backscatter so the MSE and the penalty are comparable across pixels.",
                "inputs": ["P", "scale"], "outputs": ["gtilde"],
                "lines": [
                    [{"id": "gtilde", "tex": r"\tilde{\gamma}_h", "role": "intermediate"}, {"tex": "="}, {"tex": r"\dfrac{1}{"}, {"id": "scale", "tex": r"s", "role": "intermediate"}, {"tex": r"}\;"}, {"id": "P", "tex": r"P_h", "role": "intermediate"}],
                ],
            },
            {
                "id": "peakfind", "title": "Prominence-gated peak detection", "phase": "1 - Init (CPU)",
                "note": "scipy find_peaks runs on the raw thresholded profile with no smoothing, keeping a peak only when its topographic prominence reaches p_frac = 0.05 of the max and it sits at least d_min bins from every rival; survivors are sorted by descending prominence.",
                "inputs": ["P"], "outputs": ["peaks"],
                "lines": [
                    [{"id": "peaks", "tex": r"\mathcal{P}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\left\{\,p : \mathrm{prom}(p) \ge p_{\mathrm{frac}}\,\max_h"}, {"id": "P", "tex": r"P_h", "role": "intermediate"}, {"tex": r",\ \ |p_i-p_j|\ge d_{\min}\right\},\ \ p_{\mathrm{frac}} = 0.05"}],
                ],
            },
            {
                "id": "geometry", "title": "Width scales and clamp bounds", "phase": "1 - Init (CPU)",
                "note": "The span-derived sigma_base sets the peak-separation distance d_min and, divided by D_sigma = 4, the shared initial width; the Adam width clamp runs from one elevation bin to half the height span.",
                "inputs": [], "outputs": ["sigbase", "sig0"],
                "lines": [
                    [{"id": "sigbase", "tex": r"\sigma_{\mathrm{base}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\max\!\left(2\Delta\xi,\ \tfrac{x_{\max}-x_{\min}}{8K}\right),\quad d_{\min} = \max\!\big(1,\ \lfloor \sigma_{\mathrm{base}}/\Delta\xi\rfloor\big)"}],
                    [{"id": "sig0", "tex": r"\sigma^{(0)}", "role": "intermediate"}, {"tex": "="}, {"id": "sigbase", "tex": r"\sigma_{\mathrm{base}}", "role": "intermediate"}, {"tex": r"/D_\sigma,\quad [\sigma_{\mathrm{lo}},\sigma_{\mathrm{hi}}] = \big[\Delta\xi,\ \tfrac{x_{\max}-x_{\min}}{2}\big],\ \ D_\sigma = 4"}],
                ],
            },
            {
                "id": "residfill", "title": "Residual fill of remaining slots", "phase": "1 - Init (CPU)",
                "note": "When fewer than K peaks are found, a window of half-width d_min is zeroed around each detected peak and the remaining slots are filled by repeated argmax of the residual, guaranteeing every seed is d_min apart; a flat profile (max below 1e-10) falls back to K evenly spaced indices.",
                "inputs": ["peaks", "P"], "outputs": ["idxs"],
                "lines": [
                    [{"id": "idxs", "tex": r"\mathcal{I}", "role": "intermediate"}, {"tex": "="}, {"id": "peaks", "tex": r"\mathcal{P}", "role": "intermediate"}, {"tex": r"\ \cup\ \big\{\arg\max_h\,\rho_h\big\}^{\times (K-|\mathcal{P}|)}"}],
                    [{"tex": r"\rho_h"}, {"tex": "="}, {"id": "P", "tex": r"P_h", "role": "intermediate"}, {"tex": r"\cdot\,\mathbb{1}\!\left[\min_{p\in\mathcal{P}}|h-p| > d_{\min}\right]"}],
                ],
            },
            {
                "id": "seed", "title": "Seed amplitudes and means", "phase": "1 - Init (CPU)",
                "note": "Amplitude and mean are read off the raw-profile seed indices (amplitude floored at 1e-10) as the fit's starting point; they stay frozen in the default sigma-only mode and are optimised only when the fit mode frees them. Widths all start at the shared sig0.",
                "inputs": ["idxs", "P"], "outputs": ["mu0", "a0"],
                "lines": [
                    [{"id": "mu0", "tex": r"\mu_k", "role": "intermediate"}, {"tex": "="}, {"tex": r"x_{\,\mathcal{I}_k},\qquad"}, {"id": "a0", "tex": r"a_k", "role": "intermediate"}, {"tex": "="}, {"tex": r"\max\!\big(P_{\mathcal{I}_k},\,10^{-10}\big)"}],
                ],
            },
            {
                "id": "objective", "title": "Mixture-fit objective", "phase": "2 - Fit (GPU)",
                "note": "The loss is the per-profile MSE between the K-Gaussian sum and the normalised profile, with amplitude entering normalised as a/s so the seed peak maps near unity. sigma is floored at 1e-6 and the exponent clipped to [-100, 0] before summing; vmap over pixels, value_and_grad over (a, mu, sigma).",
                "inputs": ["gtilde", "mu0", "a0", "scale", "sig0"], "outputs": ["loss"],
                "lines": [
                    [{"id": "loss", "tex": r"\mathcal{L}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\dfrac{1}{H}\sum_{h}\Big(\sum_{k}\dfrac{"}, {"id": "a0", "tex": r"a_k", "role": "intermediate"}, {"tex": r"}{"}, {"id": "scale", "tex": r"s", "role": "intermediate"}, {"tex": r"}\,e^{-\frac{(x_h-"}, {"id": "mu0", "tex": r"\mu_k", "role": "intermediate"}, {"tex": r")^2}{2\max(\sigma_k,\,10^{-6})^2}} -"}, {"id": "gtilde", "tex": r"\tilde{\gamma}_h", "role": "intermediate"}, {"tex": r"\Big)^{2}"}],
                ],
            },
            {
                "id": "adam", "title": "Bias-corrected Adam width update", "phase": "2 - Fit (GPU)",
                "note": "Hand-written bias-corrected Adam (eta = 0.2, beta_1 = 0.95, beta_2 = 0.999, eps = 1e-8) as one lax.scan over T = 3000 steps compiled into a single XLA program; sigma is always free while amplitude and mean gradients are zeroed by mask unless the mode frees them. After every step a is floored at 0, mu clipped to the height range, sigma clamped to [sigma_lo, sigma_hi].",
                "inputs": ["loss", "sig0"], "outputs": ["sigstar"],
                "iterative": {"unit": "t", "steps": 3000, "symbol": "σ",
                              "trace": ["0.62", "0.81", "1.10", "1.45", "1.70", "1.82", "1.84"]},
                "lines": [
                    [{"id": "grad", "tex": r"g_t", "role": "intermediate"}, {"tex": "="}, {"tex": r"\nabla"}, {"id": "loss", "tex": r"\mathcal{L}", "role": "intermediate"}, {"tex": r"\odot\,\mathbf{m}_{\mathrm{free}},\quad \hat m_t = \tfrac{m_t}{1-\beta_1^{t}},\ \ \hat v_t = \tfrac{v_t}{1-\beta_2^{t}}"}],
                    [{"id": "sigstar", "tex": r"\sigma^{*}_t", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathrm{clip}\!\Big("}, {"id": "sigstar", "tex": r"\sigma^{*}_{t-1}", "role": "calculated"}, {"tex": r"-\eta\,\tfrac{\hat m_t}{\sqrt{\hat v_t}+\epsilon},\ \sigma_{\mathrm{lo}},\ \sigma_{\mathrm{hi}}\Big),\ \ \eta = 0.2"}],
                ],
            },
            {
                "id": "scoreK", "title": "Per-order penalised score", "phase": "3 - Best-K",
                "note": "Every order K in 1..K_max = 5 is re-scored on the normalised profile with a flat complexity penalty lambda_K = 1e-2 per component, so an extra Gaussian is kept only when it lowers normalised MSE by at least lambda_K.",
                "inputs": ["gtilde", "sigstar", "a0"], "outputs": ["mseK", "penK"],
                "lines": [
                    [{"id": "mseK", "tex": r"\mathrm{MSE}_K", "role": "intermediate"}, {"tex": "="}, {"tex": r"\tfrac{1}{H}\sum_h\big(\hat\gamma_K(x_h) -"}, {"id": "gtilde", "tex": r"\tilde{\gamma}_h", "role": "intermediate"}, {"tex": r"\big)^2"}],
                    [{"id": "penK", "tex": r"\mathcal{L}_K", "role": "intermediate"}, {"tex": "="}, {"id": "mseK", "tex": r"\mathrm{MSE}_K", "role": "intermediate"}, {"tex": r"+\ \lambda_K\,K,\quad \lambda_K = 10^{-2}"}],
                ],
            },
            {
                "id": "selectK", "title": "Best-K argmin selection", "phase": "3 - Best-K",
                "note": "The penalised score is minimised over model order via argmin; on exact ties the smaller K wins, reinforcing parsimony. The selection is never overridden by the post-hoc ambiguity diagnostic.",
                "inputs": ["penK"], "outputs": ["Kstar"],
                "lines": [
                    [{"id": "Kstar", "tex": r"K^{*}", "role": "calculated"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,min}_{K\in\{1,\dots,K_{\max}\}}"}, {"id": "penK", "tex": r"\mathcal{L}_K", "role": "intermediate"}, {"tex": r",\quad K_{\max} = 5"}],
                ],
            },
            {
                "id": "rescale", "title": "Rescale winner to raw amplitude", "phase": "3 - Best-K",
                "note": "Scoring lives on the normalised scale, but the saved amplitudes of the winning order return to raw backscatter units; means and widths are written unchanged.",
                "inputs": ["Kstar", "a0", "scale"], "outputs": ["aout"],
                "lines": [
                    [{"id": "aout", "tex": r"a^{\mathrm{out}}_k", "role": "calculated"}, {"tex": "="}, {"id": "a0", "tex": r"a_k", "role": "intermediate"}, {"tex": r"\cdot"}, {"id": "scale", "tex": r"s", "role": "intermediate"}, {"tex": r",\qquad k \le"}, {"id": "Kstar", "tex": r"K^{*}", "role": "calculated"}],
                ],
            },
            {
                "id": "assemble", "title": "Order and pack the target", "phase": "3 - Best-K",
                "note": "The K_max slots are sorted by ascending mean elevation, with inactive slots (amplitude at or below tau_a) keyed to infinity and pushed last, then written into the interleaved 3K target; slots beyond K* are exact zeros.",
                "inputs": ["Kstar", "aout", "mu0", "sigstar"], "outputs": ["theta"],
                "lines": [
                    [{"id": "theta", "tex": r"\theta", "role": "final"}, {"tex": "="}, {"tex": r"\big[\,"}, {"id": "aout", "tex": r"a^{\mathrm{out}}", "role": "calculated"}, {"tex": ","}, {"id": "mu0", "tex": r"\mu", "role": "intermediate"}, {"tex": ","}, {"id": "sigstar", "tex": r"\sigma^{*}", "role": "calculated"}, {"tex": r"\,\big]_{\pi}^{\,k \le"}, {"id": "Kstar", "tex": r"K^{*}", "role": "calculated"}, {"tex": r"},\ \ \pi=\operatorname{argsort}_k\big(\mu_k\ \text{if}\ a_k>\tau_a\ \text{else}\ \infty\big)"}],
                ],
            },
            {
                "id": "quality", "title": "Fit-quality R-squared map", "phase": "4 - Diagnostics",
                "note": "In the inference/metrics stage, the per-pixel coefficient of determination is computed over elevation against the same thresholded-and-truncated profile the fit saw, in float64, with a 1e-12 stabiliser on the total sum of squares.",
                "inputs": ["theta", "T"], "outputs": ["r2"],
                "lines": [
                    [{"id": "r2", "tex": r"R^2", "role": "final"}, {"tex": "="}, {"tex": r"1 - \dfrac{\sum_h \big(\hat{\gamma}_h("}, {"id": "theta", "tex": r"\theta", "role": "final"}, {"tex": r") - \gamma_h\big)^2}{\sum_h (\gamma_h - \bar{\gamma})^2 + \delta},\quad \delta = 10^{-12}"}],
                ],
            },
            {
                "id": "diagnostics", "title": "K-margin and peak contrast", "phase": "4 - Diagnostics",
                "note": "Post-hoc only and never altering selection: the relative selection margin flags ambiguous pixels (below 0.05), and the uncalibrated peak-to-floor contrast uses the mean of the lowest-amplitude quartile, round(0.25 H) bins, as the noise floor.",
                "inputs": ["penK", "T"], "outputs": ["mrel"],
                "lines": [
                    [{"id": "mrel", "tex": r"m_{\mathrm{rel}}", "role": "final"}, {"tex": "="}, {"tex": r"\dfrac{\mathcal{L}_{2\mathrm{nd}} - \mathcal{L}_{K^{*}}}{\max\!\big(|\mathcal{L}_{K^{*}}|,\,10^{-12}\big)}"}],
                    [{"tex": r"C_{\mathrm{dB}}"}, {"tex": "="}, {"tex": r"10\log_{10}\dfrac{\max_h |T_h|}{\frac{1}{|\mathcal{N}|}\sum_{h\in\mathcal{N}} |T_h|},\quad |\mathcal{N}|=\mathrm{round}(0.25\,H)"}],
                ],
            },
        ]
        return {
            "key"   : "param",
            "name"  : "Parameter Extraction (K-Gaussian fit)",
            "blurb" : "Per-pixel K-Gaussian fit. Threshold and peak-normalise each elevation profile, seed a mixture from prominence peaks on the CPU, fit component widths (and, per mode, amplitudes and means) with clamped bias-corrected Adam on the GPU, select the penalised best order, sort by mean elevation into the interleaved target, then score R2 and K-margin diagnostics.",
            "nodes" : nodes,
            "steps" : steps,
        }

    def _dataset(self) -> dict:
        """Returns the flow for turning processed artifacts into normalised patch tensors."""
        nodes = [
            {"id": "Gcrop",  "tex": r"\Omega_G",           "role": "measured",     "kind": "set",    "shape": "(az0,az1,rg0,rg1)",     "desc": "global crop region in absolute pixel coords",            "sample": "(0, 4096, 0, 3000)"},
            {"id": "Rsplit", "tex": r"\Omega_s",           "role": "intermediate", "kind": "set",    "shape": "(az0,az1,rg0,rg1)",     "desc": "one split region (train/val/test)",                      "sample": "(0, 2867, 0, 3000)"},
            {"id": "azsl",   "tex": r"\sigma_a,\sigma_r",  "role": "calculated",   "kind": "set",    "shape": "slices",                "desc": "zero-based local slices into the mmap arrays",           "sample": "[0:2867], [0:3000]"},
            {"id": "sel",    "tex": r"\pi",                "role": "calculated",   "kind": "vector", "shape": "N_s",                   "desc": "positional indices of secondaries selected by label",    "sample": ["3", "5", "7", "25"]},
            {"id": "s0",     "tex": r"\mathbf{s}_0",       "role": "measured",     "kind": "matrix", "shape": "Az x Rg",               "desc": "primary (reference) complex SLC",                        "sample": [["0.8+0.2j", "0.6-0.4j"], ["0.5+0.5j", "0.9-0.1j"]]},
            {"id": "Smat",   "tex": r"S",                  "role": "measured",     "kind": "tensor", "shape": "N_s x Az x Rg",         "desc": "selected secondary complex SLC passes",                  "sample": [["0.7+0.1j"]]},
            {"id": "Imat",   "tex": r"I",                  "role": "measured",     "kind": "tensor", "shape": "N_i x Az x Rg",         "desc": "selected interferogram passes",                          "sample": [["0.9+0.4j"]]},
            {"id": "X",      "tex": r"\mathbf{X}",         "role": "measured",     "kind": "tensor", "shape": "(1+N_s+N_i) x Az x Rg", "desc": "stacked complex buffer: primary, secondaries, ifgs",     "sample": [["0.8+0.2j", "0.6-0.4j"], ["0.5+0.5j", "0.9-0.1j"]]},
            {"id": "dem",    "tex": r"\mathbf{D}",         "role": "measured",     "kind": "matrix", "shape": "Az x Rg",               "desc": "DEM elevation channel, real (optional)",                 "sample": [["112.4", "113.1"], ["110.8", "111.9"]]},
            {"id": "grid",   "tex": r"\mathcal{G}",        "role": "calculated",   "kind": "set",    "shape": "n_v x n_h",             "desc": "patch grid counts and padding",                          "sample": "n_v=89, n_h=93"},
            {"id": "cpatch", "tex": r"\mathbf{p}",         "role": "intermediate", "kind": "tensor", "shape": "C x P x P",             "desc": "one extracted complex patch (padded copy)",              "sample": [["0.8+0.2j", "0.6-0.4j", "1.1+0.0j"], ["0.5+0.5j", "0.9-0.1j", "0.7+0.3j"], ["1.0+0.2j", "0.4-0.6j", "0.8+0.1j"]]},
            {"id": "rep",    "tex": r"\mathbf{r}",         "role": "intermediate", "kind": "tensor", "shape": "c x P x P",             "desc": "real channels of one complex pass",                      "sample": ["|s|", "ang", "re", "im"]},
            {"id": "x",      "tex": r"\mathbf{x}",         "role": "calculated",   "kind": "tensor", "shape": "C_in x P x P",          "desc": "assembled real-valued input tensor",                     "sample": [["0.91", "0.62", "1.10"], ["0.55", "0.88", "0.71"]]},
            {"id": "y",      "tex": r"\mathbf{y}",         "role": "calculated",   "kind": "tensor", "shape": "C_out x P x P",         "desc": "selected Gaussian-parameter target patch",               "sample": ["a_1", "mu_1", "sig_1", "..."]},
            {"id": "xgeo",   "tex": r"\mathbf{x}'",        "role": "intermediate", "kind": "tensor", "shape": "C_in x P x P",          "desc": "geometrically augmented input (flip/rotation)",          "sample": [["0.93", "0.60", "1.08"], ["0.57", "0.86", "0.70"]]},
            {"id": "ygeo",   "tex": r"\mathbf{y}'",        "role": "intermediate", "kind": "tensor", "shape": "C_out x P x P",         "desc": "augmented target (same transform as input)",             "sample": ["a_1", "mu_1", "sig_1", "..."]},
            {"id": "gkeys",  "tex": r"g_c",                "role": "intermediate", "kind": "vector", "shape": "C_in",                  "desc": "per-channel slot keys (pass/mag, ifg/phase, ...)",       "sample": ["pass/mag", "ifg/phase", "..."]},
            {"id": "stats",  "tex": r"(\mu_c, s_c)",       "role": "calculated",   "kind": "vector", "shape": "C_in",                  "desc": "per-slot location and scale, fitted on the train split", "sample": ["0.12", "0.94", "..."]},
            {"id": "xhat",   "tex": r"\hat{\mathbf{x}}",   "role": "final",        "kind": "tensor", "shape": "C_in x P x P",          "desc": "normalised network input",                               "sample": [["0.41", "-0.20", "0.88"], ["-0.33", "0.27", "0.05"]]},
            {"id": "yhat",   "tex": r"\hat{\mathbf{y}}",   "role": "final",        "kind": "tensor", "shape": "C_out x P x P",         "desc": "normalised target",                                      "sample": ["0.30", "-0.11", "0.42"]},
            {"id": "xrec",   "tex": r"\tilde{\mathbf{x}}", "role": "calculated",   "kind": "tensor", "shape": "C_in x P x P",          "desc": "denormalised tensor (inverse; clip then expm1)",         "sample": [["0.90", "0.61"], ["0.55", "0.88"]]},
        ]
        steps = [
            {
                "id": "splitgeom", "title": "Scene split by azimuth", "phase": "Crop & split",
                "note": "The global crop is partitioned along azimuth into contiguous train/val/test bands; the standard ratio split gives 70/15/15 with no overlap and the full range extent shared.",
                "inputs": ["Gcrop"], "outputs": ["Rsplit"],
                "lines": [
                    [{"tex": r"A = \mathtt{az}_1 - \mathtt{az}_0,\quad \mathtt{az}^{\mathrm{tr}}_1 = \mathtt{az}_0 + \lfloor 0.70\,A\rfloor"}],
                    [{"id": "Rsplit", "tex": r"\Omega_s", "role": "intermediate"}, {"tex": r"\in\ \big\{[\mathtt{az}_0,\mathtt{az}^{\mathrm{tr}}_1),\ [\mathtt{az}^{\mathrm{tr}}_1,\mathtt{az}^{\mathrm{val}}_1),\ [\mathtt{az}^{\mathrm{val}}_1,\mathtt{az}_1)\big\}\times[\mathtt{rg}_0,\mathtt{rg}_1)"}],
                ],
            },
            {
                "id": "localslice", "title": "Global-to-local indexing", "phase": "Crop & split",
                "note": "Each split region's absolute bounds are shifted by the global-crop origin to give zero-based slices into the memory-mapped artifact arrays.",
                "inputs": ["Rsplit", "Gcrop"], "outputs": ["azsl"],
                "lines": [
                    [{"id": "azsl", "tex": r"\sigma_a", "role": "calculated"}, {"tex": "="}, {"tex": r"\big[\,\mathtt{az}^S_0 - \mathtt{az}^G_0,\ \ \mathtt{az}^S_1 - \mathtt{az}^G_0\,\big),\qquad A_z = \mathtt{az}^S_1-\mathtt{az}^S_0"}],
                ],
            },
            {
                "id": "secselect", "title": "Secondary selection by label", "phase": "Crop & split",
                "note": "The processed stack carries every pass; the secondary subset is chosen by flight-qualified label, mapping labels to positional indices applied to both secondaries and interferograms.",
                "inputs": ["Smat", "Imat"], "outputs": ["sel"],
                "lines": [
                    [{"id": "sel", "tex": r"\pi", "role": "calculated"}, {"tex": "="}, {"tex": r"\{\,i : \ell_i \in L_{\mathrm{req}}\,\},\qquad \ell_0 \notin L_{\mathrm{req}}"}],
                    [{"id": "Smat", "tex": r"S", "role": "measured"}, {"tex": r"\leftarrow S[\pi],\quad"}, {"id": "Imat", "tex": r"I", "role": "measured"}, {"tex": r"\leftarrow I[\pi],\quad N_s = N_i = |\pi|"}],
                ],
            },
            {
                "id": "stack", "title": "Stacked complex input buffer", "phase": "Crop & split",
                "note": "Primary, selected secondaries, and selected interferograms are written by pass-index into one pre-allocated complex buffer; the DEM and parameters are cropped to the same window but kept separate.",
                "inputs": ["s0", "Smat", "Imat"], "outputs": ["X"],
                "lines": [
                    [{"id": "X", "tex": r"\mathbf{X}[0]", "role": "measured"}, {"tex": "="}, {"id": "s0", "tex": r"\mathbf{s}_0", "role": "measured"}, {"tex": r",\quad \mathbf{X}[1:1{+}N_s] = "}, {"id": "Smat", "tex": r"S", "role": "measured"}, {"tex": r",\quad \mathbf{X}[1{+}N_s:] = "}, {"id": "Imat", "tex": r"I", "role": "measured"}],
                ],
            },
            {
                "id": "patchgrid", "title": "Sliding-window grid", "phase": "Patch extraction",
                "note": "A regular strided grid of PxP patches tiles the region; the row and column counts use a ceiling so the last window still covers the border.",
                "inputs": ["X"], "outputs": ["grid"],
                "lines": [
                    [{"tex": r"n_v = \Big\lceil \tfrac{A_z - P_H}{s}\Big\rceil + 1,\qquad n_h = \Big\lceil \tfrac{R_g - P_W}{s}\Big\rceil + 1"}],
                    [{"id": "grid", "tex": r"N_p", "role": "calculated"}, {"tex": "="}, {"tex": r"n_v \cdot n_h"}],
                ],
            },
            {
                "id": "padgeom", "title": "Symmetric boundary padding", "phase": "Patch extraction",
                "note": "The deficit between the grid's covered extent and the region is split symmetrically, with the extra pixel going to the bottom or right on odd deficits; border patches are symmetric-padded to fill the overhang.",
                "inputs": ["grid"], "outputs": ["grid"],
                "lines": [
                    [{"tex": r"p_v = P_H + (n_v - 1)\,s - A_z,\qquad p_h = P_W + (n_h - 1)\,s - R_g"}],
                    [{"tex": r"p_{\mathrm{top}} = \lfloor p_v/2\rfloor,\quad p_{\mathrm{bot}} = p_v - p_{\mathrm{top}}"}],
                ],
            },
            {
                "id": "extract", "title": "Patch extraction (contiguous copy)", "phase": "Patch extraction",
                "note": "The clipped read window is copied, never aliased, then symmetric-padded (edge-mirrored) in one pass; the same routine serves the complex stack, the parameters, and the DEM.",
                "inputs": ["X", "dem", "grid"], "outputs": ["cpatch"],
                "lines": [
                    [{"id": "cpatch", "tex": r"\mathbf{p}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{pad}\!\big("}, {"id": "X", "tex": r"\mathbf{X}", "role": "measured"}, {"tex": r"[:,\ v_0^c{:}v_1^c,\ h_0^c{:}h_1^c]\big)"}],
                ],
            },
            {
                "id": "represent", "title": "Complex to real channels", "phase": "Patch extraction",
                "note": "Each complex pass is converted to real channels by its representation mode; the default keeps magnitude for SLCs and phase for interferograms. Magnitude-normalised modes guard zero magnitude by substituting one.",
                "inputs": ["cpatch"], "outputs": ["rep"],
                "lines": [
                    [{"tex": r"\texttt{MAG}:\ (\left|\mathbf{p}\right|)\quad \texttt{ANG}:\ (\angle\mathbf{p})\quad \texttt{RI}:\ (\Re\mathbf{p},\ \Im\mathbf{p})"}],
                    [{"id": "rep", "tex": r"\mathbf{r}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\Big(\left|"}, {"id": "cpatch", "tex": r"\mathbf{p}", "role": "intermediate"}, {"tex": r"\right|,\ \tfrac{\Re\mathbf{p}}{m},\ \tfrac{\Im\mathbf{p}}{m},\ \angle\mathbf{p}\Big),\quad m=\left|\mathbf{p}\right|\ \big(\!\to 1\ \text{if}\ \left|\mathbf{p}\right|=0\big)"}],
                ],
            },
            {
                "id": "assemble_in", "title": "Input tensor assembly", "phase": "Patch extraction",
                "note": "Per patch, every enabled source is represented and concatenated along the channel axis: primary, then secondaries, then interferograms, with the optional DEM channel last; the secondary and ifg counts are independent.",
                "inputs": ["rep", "dem"], "outputs": ["x"],
                "lines": [
                    [{"id": "x", "tex": r"\mathbf{x}", "role": "calculated"}, {"tex": "="}, {"tex": r"\big[\ "}, {"id": "rep", "tex": r"\mathbf{r}_0", "role": "intermediate"}, {"tex": r"\mid \mathbf{r}_S \mid \mathbf{r}_I \mid"}, {"id": "dem", "tex": r"\mathbf{D}", "role": "measured"}, {"tex": r"\ \big]"}],
                    [{"tex": r"C_{\mathrm{in}} = c_{\mathrm{prim}} + N_s\,c_{\mathrm{sec}} + N_i\,c_{\mathrm{ifg}} + c_{\mathrm{dem}}"}],
                ],
            },
            {
                "id": "target", "title": "Target channel selection", "phase": "Patch extraction",
                "note": "The configured subset of Gaussian parameters is selected from the interleaved ground-truth layout; with all three roles enabled it keeps every channel.",
                "inputs": [], "outputs": ["y"],
                "lines": [
                    [{"id": "y", "tex": r"\mathbf{y}", "role": "calculated"}, {"tex": "="}, {"tex": r"\Theta\big[\{3g + r : g<n_g,\ r\in\mathcal{R}\}\big],\qquad C_{\mathrm{out}} = n_g\,|\mathcal{R}|"}],
                ],
            },
            {
                "id": "augment_geo", "title": "Joint geometric augmentation", "phase": "Augmentation",
                "note": "On the train split only, flips and an optional 90-degree rotation are applied with the identical transform to input and target, preserving spatial correspondence; this runs on the raw patch before normalisation.",
                "inputs": ["x", "y"], "outputs": ["xgeo", "ygeo"],
                "lines": [
                    [{"id": "xgeo", "tex": r"\mathbf{x}'", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathcal{T}\big("}, {"id": "x", "tex": r"\mathbf{x}", "role": "calculated"}, {"tex": r"\big),\qquad"}, {"id": "ygeo", "tex": r"\mathbf{y}'", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathcal{T}\big("}, {"id": "y", "tex": r"\mathbf{y}", "role": "calculated"}, {"tex": r"\big)"}],
                    [{"tex": r"\mathcal{T} \in \big\{\mathrm{flip}_H,\ \mathrm{flip}_V,\ \operatorname{rot90}^{k}\big\},\quad k\sim\mathcal{U}\{1,2,3\}"}],
                ],
            },
            {
                "id": "slotkeys", "title": "Per-channel slot assignment", "phase": "Normalization",
                "note": "Each input channel is labelled with a slot key by the same strided layout used to build the tensor, fixing which normalisation strategy each channel receives.",
                "inputs": ["x"], "outputs": ["gkeys"],
                "lines": [
                    [{"id": "gkeys", "tex": r"g_c", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{family}\,/\,\mathrm{slot}\big[\,c \bmod c_{pp}\,\big]\quad (\texttt{pass/mag},\ \texttt{ifg/phase},\ \texttt{dem/elev})"}],
                ],
            },
            {
                "id": "fitstats", "title": "Fit normalisation statistics", "phase": "Normalization",
                "note": "Statistics are fitted on the train split only, per slot, in float64 over up to 1e6 sampled values. Heavy-tailed magnitude channels (SLC/interferogram magnitude, output amplitude and sigma) use the median and IQR of their log1p values (robust-IQR-log1p); Gaussian-like channels (normalised re/im, SLC phase, output mu, DEM elevation) use the mean and standard deviation (z-score); interferogram phase is mapped by a fixed division by pi. Every fitted scale is floored at 1e-8, and output roles are fitted over active pixels only (amplitude > 1e-3).",
                "inputs": ["xgeo", "gkeys"], "outputs": ["stats"],
                "lines": [
                    [{"tex": r"f(x_c) = \log\!\big(1 + \max(x_c,0)\big)\ \ \text{(log1p slots)},\ \ \text{else } x_c"}],
                    [{"id": "stats", "tex": r"(\mu_c, s_c)", "role": "calculated"}, {"tex": "="}, {"tex": r"\big(P_{50}f,\ \max(P_{75}f{-}P_{25}f,\,10^{-8})\big)\,\text{rob},\ \ \big(\operatorname{mean} f,\ \max(\operatorname{std} f,\,10^{-8})\big)\,\text{z},\ \ (0,\ \pi)\,\text{fix}"}],
                ],
            },
            {
                "id": "normalise", "title": "Forward normalisation", "phase": "Normalization",
                "note": "The fitted statistics are applied identically to every split, yielding the dimensionless tensors the network consumes; the target is normalised the same way when output stats exist.",
                "inputs": ["xgeo", "ygeo", "stats"], "outputs": ["xhat", "yhat"],
                "lines": [
                    [{"id": "xhat", "tex": r"\hat{\mathbf{x}}", "role": "final"}, {"tex": "="}, {"tex": r"\dfrac{f("}, {"id": "xgeo", "tex": r"\mathbf{x}'", "role": "intermediate"}, {"tex": r") - "}, {"id": "stats", "tex": r"\mu_c", "role": "calculated"}, {"tex": r"}{"}, {"id": "stats", "tex": r"s_c", "role": "calculated"}, {"tex": r"},\qquad"}, {"id": "yhat", "tex": r"\hat{\mathbf{y}}", "role": "final"}, {"tex": "="}, {"tex": r"\dfrac{f(\mathbf{y}') - \mu_c}{s_c}"}],
                ],
            },
            {
                "id": "noise", "title": "Additive noise", "phase": "Normalization",
                "note": "On the train split only, Gaussian noise is added to the already-normalised input with probability p_N, so the noise std is in normalised units; noise never touches the target.",
                "inputs": ["xhat"], "outputs": ["xhat"],
                "lines": [
                    [{"id": "xhat", "tex": r"\hat{\mathbf{x}}", "role": "final"}, {"tex": r"\leftarrow"}, {"id": "xhat", "tex": r"\hat{\mathbf{x}}", "role": "final"}, {"tex": r"+\ \varepsilon,\quad \varepsilon \sim \mathcal{N}\!\big(0,\ \sigma_{\mathrm{noise}}^2 \mathbf{I}\big),\quad \sigma_{\mathrm{noise}}=0.01"}],
                ],
            },
            {
                "id": "denorm", "title": "Denormalisation (inverse)", "phase": "Inverse",
                "note": "The same per-channel statistics invert normalisation at loss and inference time; for log1p slots the log-domain argument is clipped to [log(1+floor), log(1+ceil)] with floor=0 and ceil=200 before expm1, bounding the recovered physical value to [0, 200]. Non-log1p slots flagged clampable in normalization_stats.json (out/amp, out/sigma; never out/mu) pass their affine result through the same leaky log-space barrier via compress then decompress, so the bound holds identically in every normalisation arm; each channel group is transformed by indexed selection, never by evaluating both branches of a where.",
                "inputs": ["xhat", "stats"], "outputs": ["xrec"],
                "lines": [
                    [{"id": "xrec", "tex": r"\tilde{\mathbf{x}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\operatorname{expm1}\!\big(\operatorname{clip}(\hat{x}_c s_c + \mu_c,\ \log(1{+}f),\ \log(1{+}c))\big)\ \ \text{(log1p)},\ \ \text{else } \hat{x}_c s_c + \mu_c,\quad (f,c)=(0,200)"}],
                ],
            },
        ]
        return {
            "key": "dataset", "name": "Dataset (Loaders)",
            "blurb": "Processed artifacts become PyTorch tensors: split the scene, select secondaries, stack and tile into patches, convert complex passes to real channels, assemble and augment, then apply train-fitted per-slot normalisation.",
            "nodes": nodes, "steps": steps,
        }

    def _training(self) -> dict:
        """Returns the flow for supervised backbone training of Gaussian parameters."""
        nodes = [
            {"id": "xhat",  "tex": r"\hat{\mathbf{x}}",            "role": "measured",     "kind": "tensor", "shape": "B x C_in x P x P", "desc": "normalised input batch from the loader",              "sample": [["0.41", "-0.20"], ["-0.33", "0.27"]]},
            {"id": "thn",   "tex": r"\hat{\theta}_{\mathrm{n}}",   "role": "calculated",   "kind": "tensor", "shape": "B x 3K x P x P",   "desc": "raw network output in normalised space",              "sample": ["0.78", "0.55", "0.31", "..."]},
            {"id": "thp",   "tex": r"\hat{\theta}",                "role": "calculated",   "kind": "tensor", "shape": "B x 3K x P x P",   "desc": "denormalised, physically clamped parameters",         "sample": ["12.4", "8.1", "1.9", "..."]},
            {"id": "thrn",  "tex": r"\tilde{\theta}_{\mathrm{n}}", "role": "intermediate", "kind": "tensor", "shape": "B x 3K x P x P",   "desc": "clamped params renormalised for parameter terms",     "sample": ["0.74", "0.55", "0.33", "..."]},
            {"id": "gtp",   "tex": r"\theta^{\mathrm{GT}}",        "role": "measured",     "kind": "tensor", "shape": "B x 3K x P x P",   "desc": "ground-truth Gaussian parameters, loader-normalised", "sample": ["0.55", "0.47", "0.34", "..."]},
            {"id": "yhat",  "tex": r"\hat{y}",                     "role": "intermediate", "kind": "tensor", "shape": "B x N x P x P",    "desc": "reconstructed predicted elevation curve",             "sample": [["0.05", "0.71"], ["0.33", "0.88"]]},
            {"id": "y",     "tex": r"y",                           "role": "measured",     "kind": "tensor", "shape": "B x N x P x P",    "desc": "GT elevation curve (denormalised params, no_grad)",   "sample": [["0.06", "0.70"], ["0.35", "0.86"]]},
            {"id": "err",   "tex": r"e",                           "role": "intermediate", "kind": "tensor", "shape": "B x N x P x P",    "desc": "curve-space residual y-hat minus y",                  "sample": ["-0.01", "0.01", "-0.02", "..."]},
            {"id": "Astr",  "tex": r"\mathbf{A}",                  "role": "intermediate", "kind": "matrix", "shape": "N_s x N",          "desc": "tomographic steering matrix exp(j kz xi)",            "sample": [["1+0j", "0.7+0.7j"], ["1+0j", "-0.7+0.7j"]]},
            {"id": "Rcov",  "tex": r"\mathbf{R}[P]",               "role": "intermediate", "kind": "matrix", "shape": "N_s x N_s",        "desc": "synthesised covariance A diag(P) A^H dxi",            "sample": [["3.1", "1.2+0.4j"], ["1.2-0.4j", "2.8"]]},
            {"id": "lj",    "tex": r"\ell_j",                      "role": "calculated",   "kind": "scalar", "shape": "1",                "desc": "raw value of one enabled loss term",                  "sample": "0.0317"},
            {"id": "loss",  "tex": r"\mathcal{L}",                 "role": "calculated",   "kind": "scalar", "shape": "1",                "desc": "weight-normalised composite loss",                    "sample": "4.1e-2"},
            {"id": "gnorm", "tex": r"\lVert\mathbf{g}\rVert_2",    "role": "intermediate", "kind": "scalar", "shape": "1",                "desc": "global gradient L2 norm",                             "sample": "2.7"},
            {"id": "grad",  "tex": r"\mathbf{g}",                  "role": "intermediate", "kind": "vector", "shape": "|theta|",          "desc": "clipped parameter gradient",                          "sample": ["1.2e-2", "-4e-3", "..."]},
            {"id": "eta",   "tex": r"\eta_{\mathrm{eff}}",         "role": "intermediate", "kind": "scalar", "shape": "1",                "desc": "effective LR (base x cosine x warmup)",               "sample": "7.3e-4"},
            {"id": "w",     "tex": r"\theta_t",                    "role": "intermediate", "kind": "vector", "shape": "|theta|",          "desc": "model weights at optimiser step t",                   "sample": ["0.31", "-0.08", "..."]},
            {"id": "wbest", "tex": r"\theta^{\star}",              "role": "final",        "kind": "vector", "shape": "|theta|",          "desc": "best-epoch checkpointed weights",                     "sample": ["0.30", "-0.09", "..."]},
        ]
        steps = [
            {
                "id": "forward", "title": "Forward pass", "phase": "Reconstruction",
                "note": "The backbone maps the normalised input patch to per-pixel Gaussian parameters (interleaved a, mu, sigma per component) in one forward pass, optionally under bfloat16 autocast.",
                "inputs": ["xhat"], "outputs": ["thn"],
                "lines": [
                    [{"id": "thn", "tex": r"\hat{\theta}_{\mathrm{n}}", "role": "calculated"}, {"tex": "="}, {"tex": r"f_{\theta}\!\big("}, {"id": "xhat", "tex": r"\hat{\mathbf{x}}", "role": "measured"}, {"tex": r"\big),\qquad 3K = 3\,n_g"}],
                ],
            },
            {
                "id": "tdenorm", "title": "Denormalise predictions", "phase": "Reconstruction",
                "note": "Each log1p-encoded output channel (out/amp, out/sigma) is inverted with expm1 after its pre-exponent value is clamped into [log(1+floor), log(1+ceil)] with a leaky slope of 0.1, holding the physical value inside [0, 200] while keeping a gradient outside; when a normalisation arm encodes out/amp or out/sigma without log1p, the affine result passes through the same leaky log-space barrier (compress then decompress, gated per channel by the clampable flag in normalization_stats.json). The z-scored out/mu channel is always inverted linearly.",
                "inputs": ["thn"], "outputs": ["thp"],
                "lines": [
                    [{"id": "thp", "tex": r"\hat{\theta}", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathrm{expm1}\!\big(\mathrm{clamp}_{0.1}(\hat{\theta}_{\mathrm{n}}\,s + \ell,\ [\,0,\ \log(1{+}c_{\max})\,])\big)\ \ \text{(log1p)},\ \ \text{else } \hat{\theta}_{\mathrm{n}}\,s + \ell"}],
                ],
            },
            {
                "id": "clamp", "title": "Physical parameter bounds", "phase": "Reconstruction",
                "note": "Predictions are clamped to grid-relative physical bounds with a straight-through leaky slope of 0.1, so the amplitude, mu and sigma heads keep a small gradient through saturation.",
                "inputs": ["thp"], "outputs": ["thp"],
                "lines": [
                    [{"id": "thp", "tex": r"\hat{a}_k \in [0,a_{\max}],\ \ \hat{\mu}_k \in [x_{\min},x_{\max}],\ \ \hat{\sigma}_k \in \big[\tfrac{\Delta x}{2},\tfrac{x_{\max}-x_{\min}}{2}\big]", "role": "calculated"}],
                    [{"tex": r"\mathrm{clamp}_{\mathrm{leaky}}(x) = \mathrm{clip}(x) + 0.1\,\big(x - \mathrm{clip}(x)\big),\qquad a_{\max}=200"}],
                ],
            },
            {
                "id": "renorm", "title": "Renormalise for parameter terms", "phase": "Reconstruction",
                "note": "The clamped physical predictions are mapped back to training space so the parameter-space loss terms operate in the same normalised units as the labels.",
                "inputs": ["thp"], "outputs": ["thrn"],
                "lines": [
                    [{"id": "thrn", "tex": r"\tilde{\theta}_{\mathrm{n}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\big(\log\!1\mathrm{p}("}, {"id": "thp", "tex": r"\hat{\theta}", "role": "calculated"}, {"tex": r") - \ell\big)\,/\,s\ \ \text{(log1p)},\ \ \text{else } (\hat{\theta} - \ell)/s"}],
                ],
            },
            {
                "id": "reconstruct", "title": "Gaussian curve reconstruction", "phase": "Reconstruction",
                "note": "Ground truth is denormalised under no_grad, then both the predicted physical parameters and the GT are evaluated on the elevation axis as an additive Gaussian mixture; the exponent is floored at -100 and sigma at 1e-6.",
                "inputs": ["thp", "gtp"], "outputs": ["yhat", "y"],
                "lines": [
                    [{"id": "yhat", "tex": r"\hat{y}(x_n)", "role": "intermediate"}, {"tex": "="}, {"tex": r"\sum_{k}"}, {"id": "thp", "tex": r"\hat{a}_k", "role": "calculated"}, {"tex": r"\exp\!\Big(-\tfrac{(x_n-\hat{\mu}_k)^2}{2\hat{\sigma}_k^2}\Big),\qquad K = C/3"}],
                ],
            },
            {
                "id": "residual", "title": "Curve residual", "phase": "Curve loss",
                "note": "The elementwise residual is computed once when any pointwise curve term is enabled, and shared by the MSE, L1, Huber and Charbonnier terms; shape-sensitive terms take the curves directly.",
                "inputs": ["yhat", "y"], "outputs": ["err"],
                "lines": [
                    [{"id": "err", "tex": r"e", "role": "intermediate"}, {"tex": "="}, {"id": "yhat", "tex": r"\hat{y}", "role": "intermediate"}, {"tex": r"\ -\ "}, {"id": "y", "tex": r"y", "role": "measured"}],
                ],
            },
            {
                "id": "curvepoint", "title": "Pointwise curve terms", "phase": "Curve loss",
                "note": "Four optional pointwise reductions of the shared residual, each averaged over all elements; Huber transitions at delta=1.0 and Charbonnier uses an epsilon=1e-3 smoothed L1.",
                "inputs": ["err"], "outputs": ["lj"],
                "lines": [
                    [{"tex": r"\ell_{\mathrm{MSE}} = \big\langle e^2\big\rangle,\qquad \ell_{L1} = \big\langle |e| \big\rangle"}],
                    [{"id": "lj", "tex": r"\ell_{\mathrm{Hub}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\big\langle \tfrac12 e^2\,[|e|\le\delta] + \delta(|e|-\tfrac{\delta}{2})\,[|e|>\delta]\big\rangle"}],
                    [{"tex": r"\ell_{\mathrm{Charb}} = \big\langle \sqrt{e^2 + \varepsilon^2}\big\rangle"}],
                ],
            },
            {
                "id": "curveshape", "title": "Shape-sensitive curve term", "phase": "Curve loss",
                "note": "The default curve objective: cosine distance over pixels whose GT curve norm exceeds 1e-3, penalising profile shape rather than magnitude (weight 0.05 in the default curriculum).",
                "inputs": ["yhat", "y"], "outputs": ["lj"],
                "lines": [
                    [{"id": "lj", "tex": r"\ell_{\cos}", "role": "calculated"}, {"tex": "="}, {"tex": r"\Big\langle 1 - \tfrac{\langle\hat{y},y\rangle}{\lVert\hat{y}\rVert\,\lVert y\rVert}\Big\rangle_{\lVert y\rVert>10^{-3}}"}],
                ],
            },
            {
                "id": "physgeom", "title": "Tomographic forward operator", "phase": "Physics loss",
                "note": "The physics terms share a Fourier forward operator. Under the default height convention the wavenumber uses the round-trip 4-pi/(lambda r0) factor divided by the look-angle sine, with the master-relative perpendicular baseline; when any physics term is active a per-pixel kz field replaces this single shared steering matrix.",
                "inputs": [], "outputs": ["Astr"],
                "lines": [
                    [{"tex": r"b_\perp = h\cos\theta + v\sin\theta,\qquad k_z^{(i)} = \dfrac{4\pi\, b_\perp^{(i)}}{\lambda\, r_0\, \sin\theta}"}],
                    [{"id": "Astr", "tex": r"A_{in}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\exp\!\big(j\,k_z^{(i)}\,\xi_n\big)"}],
                ],
            },
            {
                "id": "physmoments", "title": "Power and moment terms", "phase": "Physics loss",
                "note": "Optional ratio-based terms compare the relative integrated power and the first three profile moments (mass, centroid, spread) with unit moment weights, reduced over pixels whose GT power exceeds the physics floor 1e-3.",
                "inputs": ["yhat", "y"], "outputs": ["lj"],
                "lines": [
                    [{"tex": r"m_0 = \textstyle\sum_n P_n\,\Delta\xi,\quad \bar z = \tfrac{\sum_n P_n \xi_n}{\sum_n P_n},\quad \sigma_z = \sqrt{\tfrac{\sum_n P_n \xi_n^2}{\sum_n P_n} - \bar z^2 + 10^{-8}}"}],
                    [{"id": "lj", "tex": r"\ell_{\mathrm{mom}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\Big\langle \tfrac{w_0\frac{|\Delta m_0|}{m_0^T} + w_1\frac{|\Delta\bar z|}{\xi_{\max}-\xi_{\min}} + w_2\frac{|\Delta\sigma_z|}{\xi_{\max}-\xi_{\min}}}{w_0+w_1+w_2}\Big\rangle"}],
                ],
            },
            {
                "id": "physcov", "title": "Coherence and covariance matching", "phase": "Physics loss",
                "note": "The two default physics terms (weight 0.05 each in the complete curriculum): coherence re-synthesis compares the mass-normalised characteristic functions of the two profiles; covariance matching exploits R's linearity to transform only the difference, both insensitive to absolute power.",
                "inputs": ["yhat", "y", "Astr"], "outputs": ["Rcov", "lj"],
                "lines": [
                    [{"tex": r"\gamma_P(k_z^{(i)}) = \tfrac{\sum_n P_n e^{j k_z^{(i)}\xi_n}}{\sum_n P_n},\qquad \ell_{\mathrm{coh}} = \big\langle \tfrac{1}{N_s}\textstyle\sum_i |\gamma_P^{(i)} - \gamma_T^{(i)}|^2\big\rangle"}],
                    [{"id": "Rcov", "tex": r"\mathbf{R}[P]", "role": "intermediate"}, {"tex": "="}, {"id": "Astr", "tex": r"\mathbf{A}", "role": "intermediate"}, {"tex": r"\,\mathrm{diag}(P)\,\mathbf{A}^H\Delta\xi,\quad \ell_{\mathrm{cov}} = \big\langle \tfrac{\lVert\mathbf{R}[P]-\mathbf{R}[T]\rVert_F^2}{\lVert\mathbf{R}[T]\rVert_F^2}\big\rangle"}],
                ],
            },
            {
                "id": "physcapon", "title": "Capon cycle-consistency", "phase": "Physics loss",
                "note": "The most expensive, opt-in physics term synthesises the covariance from the predicted profile, adds signal-adaptive diagonal loading (epsilon=1e-2 times mean trace), Hermitianises, then forms the Capon spectrum by solving the loaded system and compares mass-normalised spectra.",
                "inputs": ["Rcov", "Astr", "y"], "outputs": ["lj"],
                "lines": [
                    [{"tex": r"\hat{T}_P(\xi_n) = \dfrac{1}{\mathbf{a}^H(\xi_n)\big("}, {"id": "Rcov", "tex": r"\mathbf{R}[P]", "role": "intermediate"}, {"tex": r" + \epsilon\bar\sigma\mathbf{I}\big)^{-1}\mathbf{a}(\xi_n)},\quad \bar\sigma = \tfrac{1}{N_s}\mathrm{tr}\,\mathbf{R}[P]"}],
                    [{"id": "lj", "tex": r"\ell_{\mathrm{cyc}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\Big\langle \tfrac{1}{N}\textstyle\sum_n\big(\tfrac{\hat{T}_P(\xi_n)}{m_0^{\hat T}} - \tfrac{T(\xi_n)}{m_0^{T}}\big)^2\Big\rangle"}],
                ],
            },
            {
                "id": "paramterms", "title": "Parameter-space terms", "phase": "Parameter loss",
                "note": "The default hungarian matching first orders GT slots by mu among active components (amplitudes at or below amp_zero_thr = 1e-4 pushed to the end), then permutes each pixel's predicted slots onto the GT slots by the optimal assignment, found by enumerating all K! permutations of the active-weighted L1 cost; the loss is therefore invariant to the predicted slot order. Under the opt-in sorted_gt mode the GT sort still happens but predictions keep their slot order, so each slot learns a fixed height rank. Inactive slots mask their mu and sigma to zero so empty slots contribute amplitude only. Param-L1 (the default supervised term) is active-normalised in normalised space; TV is an optional roughness penalty.",
                "inputs": ["thrn", "gtp"], "outputs": ["lj"],
                "lines": [
                    [{"tex": r"\pi^{\star} = \operatorname*{arg\,min}_{\pi \in S_K}\ \textstyle\sum_k \mathbb{1}[a^{\mathrm{GT}}_k > 10^{-4}]\,\big|\tilde{\theta}_{\pi(k)} - \theta^{\mathrm{GT}}_{k}\big|_1"}],
                    [{"id": "lj", "tex": r"\ell_{\mathrm{p\text{-}L1}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{\sum w_p\,m\,|\,\tilde{\theta}_{\mathrm{n}} - \theta^{\mathrm{GT}}\,|}{\sum w_p\,m},\quad m = \mathbb{1}[a^{\mathrm{GT}} > 10^{-4}]\ (\mu,\sigma)"}],
                    [{"tex": r"\ell_{\mathrm{TV}} = \overline{|\tilde\theta_{h}-\tilde\theta_{h-1}|} + \overline{|\tilde\theta_{w}-\tilde\theta_{w-1}|}"}],
                ],
            },
            {
                "id": "composite", "title": "Composite weighted loss", "phase": "Composite",
                "note": "The total loss is the weight-normalised sum over enabled terms; each weight is the user-selected weight_* value directly (no automatic normaliser). The loss-scale probe can suggest factors to fold into those weights, but the user brings heterogeneous terms to comparable magnitude.",
                "inputs": ["lj"], "outputs": ["loss"],
                "lines": [
                    [{"id": "loss", "tex": r"\mathcal{L}", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{\sum_j \alpha_j\,"}, {"id": "lj", "tex": r"\ell_j", "role": "calculated"}, {"tex": r"}{\sum_j \alpha_j},\qquad \alpha_j = \mathtt{weight\_}j"}],
                ],
            },
            {
                "id": "gradclip", "title": "Backprop and gradient clipping", "phase": "Optimiser step",
                "note": "Non-finite batches are skipped (or abort training); surviving gradients are rescaled by a common factor so the global L2 norm never exceeds the threshold, which is fixed at 1.0 or an adaptive percentile / mean-plus-k-sigma over a 200-step window.",
                "inputs": ["loss"], "outputs": ["gnorm", "grad"],
                "lines": [
                    [{"id": "gnorm", "tex": r"\lVert\mathbf{g}\rVert_2", "role": "intermediate"}, {"tex": "="}, {"tex": r"\Big(\textstyle\sum_i \lVert\nabla_{\theta^{(i)}}\mathcal{L}\rVert_2^2\Big)^{1/2}"}],
                    [{"id": "grad", "tex": r"\mathbf{g}", "role": "intermediate"}, {"tex": r"\leftarrow \mathbf{g}\cdot\min\!\Big(1,\ \tfrac{\tau}{\lVert\mathbf{g}\rVert_2 + \varepsilon}\Big),\quad \tau\in\{1.0,\ P_{95},\ \bar g + k\sigma_g\}"}],
                ],
            },
            {
                "id": "adamw", "title": "AdamW update", "phase": "Optimiser step",
                "note": "Bias-corrected adaptive moments (betas 0.9/0.999, eps 1e-8) with per-group learning rates and per-group decoupled weight decay (1e-4 for the UNet, UNet-skip and ResUNet families, 5e-3 or 1e-2 for some transformer backbones); the OptimizerConfig.weight_decay = 0.1 field is only a fallback for groups that carry no decay of their own, which no architecture config leaves unset. The epoch loop drives the training loss down over many steps, with optional EMA shadow weights.",
                "inputs": ["grad", "eta"], "outputs": ["w"],
                "iterative": {"var": "loss", "steps": 60, "unit": "epoch", "symbol": "L",
                              "trace": ["4.1e-2", "2.7e-2", "1.9e-2", "1.4e-2", "1.1e-2", "9.6e-3"]},
                "lines": [
                    [{"tex": r"\hat m_t = \tfrac{m_t}{1-\beta_1^t},\quad \hat v_t = \tfrac{v_t}{1-\beta_2^t}"}],
                    [{"id": "w", "tex": r"\theta_{t+1}", "role": "intermediate"}, {"tex": "="}, {"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": r"\ -\ \eta_{\mathrm{eff}}\Big(\tfrac{\hat m_t}{\sqrt{\hat v_t}+\epsilon} + \lambda\theta_t\Big)"}],
                ],
            },
            {
                "id": "schedule", "title": "Warmup, cosine schedule, curriculum", "phase": "Schedule & curriculum",
                "note": "Each group's effective LR is its base rate times the per-epoch cosine factor (T = scheduler.epochs, which ConfigFactory installs from training.epochs = 60 unless scheduler_epochs is set, so the standalone SchedulerConfig default of 100 is never what a run gets; eta_min = 1e-6) times the per-step warmup factor (200 steps from start factor 0.1); at swap epoch 15 the loss curriculum moves from the warmup objective to the complete objective, and with the curriculum disabled the complete objective runs from the first epoch.",
                "inputs": [], "outputs": ["eta"],
                "lines": [
                    [{"tex": r"F(t) = \tfrac{\eta_{\min}}{\eta_0} + \tfrac12\big(1 - \tfrac{\eta_{\min}}{\eta_0}\big)\big(1 + \cos\tfrac{\pi\min(t,T)}{T}\big)"}],
                    [{"id": "eta", "tex": r"\eta_{\mathrm{eff}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\eta_0\cdot F(t)\cdot f_{\mathrm{warmup}}(s),\qquad f_{\mathrm{warmup}}(s) = \alpha_0 + (1-\alpha_0)\tfrac{s}{S}"}],
                ],
            },
            {
                "id": "checkpoint", "title": "Validation and checkpoint", "phase": "Eval & checkpoint",
                "note": "Evaluation runs every validation_frequency epochs, which the entry point sets to 1 (EMA weights when enabled); the best epoch is checkpointed on strict improvement and early stopping reverts to it after early_stop_patience = 30 evaluations without a new minimum. The best-loss baseline resets across a curriculum swap.",
                "inputs": ["w"], "outputs": ["wbest"],
                "lines": [
                    [{"id": "wbest", "tex": r"\theta^{\star}", "role": "final"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,min}_{t}\ \mathcal{L}_{\mathrm{val}}("}, {"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": r")"}],
                ],
            },
        ]
        return {
            "key": "training", "name": "Training (Supervised backbone)",
            "blurb": "One forward pass predicts all Gaussian parameters; predictions are denormalised, physically clamped and renormalised, then a weight-normalised composite over curve, parameter and optional physics terms is backpropagated through AdamW with linear warmup, cosine annealing, a two-phase loss curriculum, gradient clipping and early stopping.",
            "nodes": nodes, "steps": steps,
        }

    def _dual_train(self) -> dict:
        """Returns the flow for dual-trunk training with separate parameter and existence trunks."""
        nodes = [
            {"id": "xhat",   "tex": r"\hat{\mathbf{x}}",          "role": "measured",     "kind": "tensor", "shape": "B x C_in x P x P", "desc": "normalised input batch: primary magnitude, secondary magnitudes, interferogram phases", "sample": [["0.41", "-0.20"], ["-0.33", "0.27"]]},
            {"id": "keys",   "tex": r"\mathcal{K}",               "role": "intermediate", "kind": "vector", "shape": "C_in",             "desc": "per-channel group keys from InputConfig.channel_group_keys",                            "sample": ["pass/mag", "pass/mag", "ifg/angle", "..."]},
            {"id": "xp",     "tex": r"\hat{\mathbf{x}}^{P}",      "role": "intermediate", "kind": "tensor", "shape": "B x C_P x P x P",  "desc": "channels routed to the parameter trunk (params_input groups)",                          "sample": [["0.41", "-0.20"], ["0.15", "0.62"]]},
            {"id": "xe",     "tex": r"\hat{\mathbf{x}}^{E}",      "role": "intermediate", "kind": "tensor", "shape": "B x C_E x P x P",  "desc": "channels routed to the existence trunk (existence_input groups)",                       "sample": [["0.41", "-0.20"], ["0.15", "0.62"]]},
            {"id": "zp",     "tex": r"\mathbf{z}^{P}",            "role": "calculated",   "kind": "tensor", "shape": "B x D_P x P x P",  "desc": "parameter-trunk decoder embedding (headless backbone output)",                          "sample": [["0.72", "0.11"], ["-0.34", "0.58"]]},
            {"id": "ze",     "tex": r"\mathbf{z}^{E}",            "role": "calculated",   "kind": "tensor", "shape": "B x D_E x P x P",  "desc": "existence-trunk decoder embedding (headless backbone output)",                          "sample": [["0.19", "-0.42"], ["0.63", "0.07"]]},
            {"id": "uk",     "tex": r"\mathbf{u}_k",              "role": "intermediate", "kind": "tensor", "shape": "B x K x 3 x P x P","desc": "per-slot head output: raw amplitude, mu and sigma in normalised space",                 "sample": [["0.83", "0.55", "0.31"], ["0.12", "0.74", "0.44"]]},
            {"id": "gate",   "tex": r"\mathbf{g}",                "role": "calculated",   "kind": "tensor", "shape": "B x K x P x P",    "desc": "per-slot existence gate in (0, 1) from the existence trunk",                            "sample": [["0.97", "0.04"], ["0.91", "0.62"]]},
            {"id": "aoff",   "tex": r"\mathbf{b}",                "role": "intermediate", "kind": "vector", "shape": "K",                "desc": "learned closed-gate amplitude offset amp_off, initialised to zero",                     "sample": ["-0.02", "0.01"]},
            {"id": "thn",    "tex": r"\hat{\theta}_{\mathrm{n}}", "role": "calculated",   "kind": "tensor", "shape": "B x 3K x P x P",   "desc": "interleaved normalised parameter output, identical in layout to the backbone output",   "sample": ["0.81", "0.55", "0.31", "..."]},
            {"id": "loss",   "tex": r"\mathcal{L}",               "role": "calculated",   "kind": "scalar", "shape": "1",                "desc": "weight-normalised composite loss, the same catalog the backbone uses",                  "sample": "4.4e-2"},
            {"id": "groups", "tex": r"\{g_P, g_E, g_H\}",         "role": "intermediate", "kind": "set",    "shape": "3",                "desc": "AdamW parameter groups: parameter trunk, existence trunk, output head",                 "sample": ["params_trunk", "existence_trunk", "output_head"]},
            {"id": "wbest",  "tex": r"\theta^{\star}",            "role": "final",        "kind": "vector", "shape": "|theta|",          "desc": "best-epoch checkpointed dual-trunk weights",                                            "sample": ["0.30", "-0.09", "..."]},
        ]
        steps = [
            {
                "id": "dual_keys", "title": "Channel group keys", "phase": "A - Input routing",
                "note": "The dataset stack labels every input channel with a group key: the primary magnitude and the secondary magnitudes are pass/*, the interferogram channels are ifg/*, and the elevation channel is dem/* when input.use_dem is on. TrunkChannelMap infers the track count that reproduces in_channels under the active InputConfig and raises when that count is not unique.",
                "inputs": ["xhat"], "outputs": ["keys"],
                "lines": [
                    [{"id": "keys", "tex": r"\mathcal{K}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\big(\underbrace{\mathtt{pass}/\ast}_{1 + N_s},\ \underbrace{\mathtt{ifg}/\ast}_{N_i}\big),\qquad C_{\mathrm{in}} = 1 + N_s + N_i = 9\ \text{for the default stack}"}],
                ],
            },
            {
                "id": "dual_route", "title": "Trunk input routing", "phase": "A - Input routing",
                "note": "params_input and existence_input each select a subset of the groups {pass, ifg, dem}; the resolved index tuples are stored as the params_channels and existence_channels buffers and applied with index_select. A selected group without channels in the stack contributes nothing, so dem only adds a channel when input.use_dem is on. The shipped default is full-full, meaning both trunks see every available channel; the routing trials mode enumerates the seven variants (pass-full, full-pass, ifg-full, full-ifg, pass-ifg, ifg-pass and full-full).",
                "inputs": ["xhat", "keys"], "outputs": ["xp", "xe"],
                "lines": [
                    [{"id": "xp", "tex": r"\hat{\mathbf{x}}^{P}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\hat{\mathbf{x}}\big[\,\mathcal{C}_P\,\big],\qquad \mathcal{C}_P = \{\,c : \mathrm{group}(\mathcal{K}_c) \in \mathtt{params\_input}\,\}"}],
                    [{"id": "xe", "tex": r"\hat{\mathbf{x}}^{E}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\hat{\mathbf{x}}\big[\,\mathcal{C}_E\,\big],\qquad \mathcal{C}_E = \{\,c : \mathrm{group}(\mathcal{K}_c) \in \mathtt{existence\_input}\,\}"}],
                ],
            },
            {
                "id": "dual_trunks", "title": "Two independent trunks", "phase": "B - Trunks",
                "note": "Each trunk is any architecture from the backbone zoo, built with head = 'none' so its encode_decode returns the decoder embedding instead of parameters. The trunks share no weights and no activations. Both default to unet_skip; params_features and existence_features resize their feature ladders, and per-trunk overrides reach any remaining field of the trunk config except the six reserved ones the dual model sets itself (in_channels, out_channels, params_per_gaussian, head, init_mode, features).",
                "inputs": ["xp", "xe"], "outputs": ["zp", "ze"],
                "lines": [
                    [{"id": "zp", "tex": r"\mathbf{z}^{P}", "role": "calculated"}, {"tex": "="}, {"tex": r"f_{P}\big("}, {"id": "xp", "tex": r"\hat{\mathbf{x}}^{P}", "role": "intermediate"}, {"tex": r"\big),\qquad"}, {"id": "ze", "tex": r"\mathbf{z}^{E}", "role": "calculated"}, {"tex": "="}, {"tex": r"f_{E}\big("}, {"id": "xe", "tex": r"\hat{\mathbf{x}}^{E}", "role": "intermediate"}, {"tex": r"\big)"}],
                    [{"tex": r"\text{features}_P = [64, 128, 248, 472],\quad \text{features}_E = [24, 48, 84, 156]\ \Rightarrow\ D_P = 64,\ D_E = 24"}],
                ],
            },
            {
                "id": "dual_capacity", "title": "Capacity split between the arms", "phase": "B - Trunks",
                "note": "The two feature ladders set how the parameter budget is divided. The shipped defaults are the 90-10 rung of ratio_trials: 28.06 M weights in the parameter arm (parameter trunk plus the per-slot heads) against 3.12 M in the existence arm (existence trunk, existence head and amp_off), an exact 90.0 / 10.0 split. The ratio trials mode sweeps 50-50, 60-40, 70-30, 80-20 and 90-10 at a matched total, with match_tolerance = 0.01 guarding the parity.",
                "inputs": ["zp", "ze"], "outputs": ["zp", "ze"],
                "lines": [
                    [{"tex": r"\rho = \dfrac{|f_P| + |h_{1..K}|}{|f_P| + |h_{1..K}| + |f_E| + |h_{\mathrm{ex}}| + K} = \dfrac{28.06\,\mathrm{M}}{31.18\,\mathrm{M}} = 0.900"}],
                ],
            },
            {
                "id": "dual_heads", "title": "Per-slot parameter heads", "phase": "C - Dual set-prediction head",
                "note": "The parameter embedding feeds K independent pixelwise MLPs, one per Gaussian slot, each a 1x1 convolution to max(D_P/2, 16) hidden channels, a ReLU and a 1x1 convolution to the three parameters of that slot. set_pred is the only head the dual model accepts; any other head value raises at construction.",
                "inputs": ["zp"], "outputs": ["uk"],
                "lines": [
                    [{"id": "uk", "tex": r"\mathbf{u}_k", "role": "intermediate"}, {"tex": "="}, {"tex": r"W^{(k)}_2\,\mathrm{ReLU}\big(W^{(k)}_1\,"}, {"id": "zp", "tex": r"\mathbf{z}^{P}", "role": "calculated"}, {"tex": r" + b^{(k)}_1\big) + b^{(k)}_2,\qquad k = 1,\dots,K"}],
                ],
            },
            {
                "id": "dual_gate", "title": "Existence gate and amplitude blend", "phase": "C - Dual set-prediction head",
                "note": "The existence embedding feeds one pixelwise MLP that emits K logits, squashed by a sigmoid into per-slot occupancy gates. Only the amplitude channel is gated: it is a convex blend of the predicted amplitude and the learned per-slot offset amp_off, so a closed gate drives the slot towards its learned empty value while mu and sigma pass through untouched. The split lets the occupancy decision and the placement decision read different channels and be sized independently: the routing trials vary which groups feed which trunk, the ratio trials vary how much capacity each arm gets.",
                "inputs": ["ze", "uk", "aoff"], "outputs": ["gate", "thn"],
                "lines": [
                    [{"id": "gate", "tex": r"\mathbf{g}", "role": "calculated"}, {"tex": "="}, {"tex": r"\sigma\big(h_{\mathrm{ex}}("}, {"id": "ze", "tex": r"\mathbf{z}^{E}", "role": "calculated"}, {"tex": r")\big) \in (0,1)^{K}"}],
                    [{"tex": r"\hat{a}_k = g_k\,u_{k,1} + (1 - g_k)\,"}, {"id": "aoff", "tex": r"b_k", "role": "intermediate"}, {"tex": r",\qquad (\hat{\mu}_k, \hat{\sigma}_k) = (u_{k,2},\ u_{k,3})"}],
                ],
            },
            {
                "id": "dual_assemble", "title": "Interleaved output tensor", "phase": "C - Dual set-prediction head",
                "note": "The gated slots are stacked and flattened back into the interleaved 3K channel layout the rest of the stack expects, so everything downstream (denormalisation, physical clamping, the loss catalog, inference, the cube explorer) treats a dual run exactly like a backbone run.",
                "inputs": ["gate", "uk"], "outputs": ["thn"],
                "lines": [
                    [{"id": "thn", "tex": r"\hat{\theta}_{\mathrm{n}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\big(\hat{a}_1, \hat{\mu}_1, \hat{\sigma}_1,\ \dots,\ \hat{a}_K, \hat{\mu}_K, \hat{\sigma}_K\big),\qquad 3K = C_{\mathrm{out}}"}],
                ],
            },
            {
                "id": "dual_loss", "title": "Shared composite loss", "phase": "D - Loss and optimisation",
                "note": "The dual curriculum is the backbone curriculum: the same two-phase warmup and complete stages, the same weight-normalised composite over curve, parameter and optional physics terms, and hungarian matching in both stages. The full training flow documents every term; nothing in the loss is dual-specific.",
                "inputs": ["thn"], "outputs": ["loss"],
                "lines": [
                    [{"id": "loss", "tex": r"\mathcal{L}", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{\sum_j \alpha_j\,\ell_j}{\sum_j \alpha_j},\qquad \text{matching} = \mathtt{hungarian}"}],
                ],
            },
            {
                "id": "dual_groups", "title": "Three-group AdamW", "phase": "D - Loss and optimisation",
                "note": "get_param_groups splits the model into the parameter trunk, the existence trunk and the output head, each with its own learning rate and weight decay (3e-4 / 3e-4 / 1e-3 and 1e-4 throughout). All six values are exposed to the tuner over a log-uniform range. Warmup, cosine annealing, gradient clipping, EMA, early stopping and checkpointing are the shared trainer components.",
                "inputs": ["loss"], "outputs": ["groups", "wbest"],
                "lines": [
                    [{"id": "groups", "tex": r"\{g_P, g_E, g_H\}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\big\{(f_P;\ 3\!\times\!10^{-4}, 10^{-4}),\ (f_E;\ 3\!\times\!10^{-4}, 10^{-4}),\ (h;\ 10^{-3}, 10^{-4})\big\}"}],
                    [{"id": "wbest", "tex": r"\theta^{\star}", "role": "final"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,min}_{t}\ \mathcal{L}_{\mathrm{val}}(\theta_t)"}],
                ],
            },
            {
                "id": "dual_persist", "title": "Run naming, persistence and trials", "phase": "E - Run artifacts",
                "note": "The run name carries both trunks: dual_<params>.<existence>, collapsed to dual_<backbone> when they match, followed by the head, matching, slot count, augmentation and presence tags and a routing tag built from the two group labels (full.full by default). DualModelConfigIO writes dual_model_config.json under meta/ so inference reconstructs both trunks faithfully. Beyond the shared trial modes, the dual scheduler adds routing (which channel groups feed which trunk) and ratio (how the parameter budget splits).",
                "inputs": ["wbest"], "outputs": ["wbest"],
                "lines": [
                    [{"tex": r"\texttt{dual\_unet\_skip-set\_pred-hungarian-K2-...-full.full}"}],
                ],
            },
        ]
        return {
            "key": "dual_train", "name": "Dual Trunks (Train)",
            "blurb": "Two independent backbones read their own slice of the input stack: the parameter trunk feeds K per-slot MLP heads that place the Gaussians, the existence trunk feeds one head whose sigmoid gate decides which slots are occupied, and the gate blends each amplitude with a learned empty-slot offset. The output is the same interleaved 3K tensor a backbone produces, so the loss catalog, the curriculum and the whole inference stack are shared; only the routing of channels to trunks and the capacity split between the two arms are new axes.",
            "nodes": nodes, "steps": steps,
        }

    def _profile_ae_train(self) -> dict:
        """Returns the flow for training the profile autoencoder on elevation curves."""
        nodes = [
            {"id": "params", "tex": r"\Theta",                    "role": "measured",     "kind": "tensor", "shape": "3K x Az x Rg", "desc": "per-pixel Gaussian mixture parameters (a, mu, sigma) from extraction", "sample": [["0.81", "12.4", "1.9"], ["0.55", "31.8", "2.6"]]},
            {"id": "gp",     "tex": r"(a,\mu,\sigma)",            "role": "intermediate", "kind": "tensor", "shape": "3 x N_p x K",  "desc": "de-interleaved per-pixel amplitudes, means and widths",                "sample": [["0.81", "0.55"], ["12.4", "31.8"], ["1.9", "2.6"]]},
            {"id": "active", "tex": r"\mathbb{1}_{\mathrm{act}}", "role": "intermediate", "kind": "vector", "shape": "N_p",          "desc": "active-pixel mask: any component amplitude above threshold",           "sample": ["1", "0", "1", "1"]},
            {"id": "idx",    "tex": r"\mathcal{I}",               "role": "calculated",   "kind": "vector", "shape": "N_keep",       "desc": "kept, shuffled pixel indices (subsampled active + empty frac)",        "sample": ["4", "1", "9", "2"]},
            {"id": "curve",  "tex": r"\mathbf{c}",                "role": "calculated",   "kind": "vector", "shape": "L",            "desc": "synthesised elevation profile, the autoencoder sample",                "sample": ["0.00", "0.62", "0.31", "0.88", "0.00"]},
            {"id": "caug",   "tex": r"\mathbf{c}'",               "role": "intermediate", "kind": "vector", "shape": "L",            "desc": "geometrically augmented profile (scale, shift, flip)",                 "sample": ["0.00", "0.68", "0.34", "0.80", "0.00"]},
            {"id": "stats",  "tex": r"(\ell, s)",                 "role": "calculated",   "kind": "vector", "shape": "2",            "desc": "log1p-standardize location and scale, fitted on the train split",      "sample": ["0.32", "0.51"]},
            {"id": "cn",     "tex": r"\hat{\mathbf{c}}",          "role": "calculated",   "kind": "vector", "shape": "L",            "desc": "normalised profile: network input and reconstruction target",          "sample": ["-0.63", "0.58", "-0.10", "1.20", "-0.63"]},
            {"id": "z",      "tex": r"\mathbf{z}",                "role": "intermediate", "kind": "vector", "shape": "d",            "desc": "raw encoder bottleneck embedding",                                     "sample": ["0.22", "-1.10", "0.70", "..."]},
            {"id": "zn",     "tex": r"\hat{\mathbf{z}}",          "role": "calculated",   "kind": "vector", "shape": "d",            "desc": "normalised bottleneck embedding",                                      "sample": ["0.18", "-0.94", "0.61", "..."]},
            {"id": "crec",   "tex": r"\tilde{\mathbf{c}}",        "role": "calculated",   "kind": "vector", "shape": "L",            "desc": "decoder-reconstructed profile",                                        "sample": ["-0.60", "0.55", "-0.08", "1.17", "-0.61"]},
            {"id": "err",    "tex": r"e",                         "role": "intermediate", "kind": "vector", "shape": "L",            "desc": "reconstruction residual c-rec minus c-hat",                            "sample": ["0.03", "-0.03", "0.02", "-0.03", "0.02"]},
            {"id": "loss",   "tex": r"\mathcal{L}",               "role": "calculated",   "kind": "scalar", "shape": "1",            "desc": "single-term reconstruction loss",                                      "sample": "3.1e-2"},
            {"id": "groups", "tex": r"\{g_e, g_n, g_d\}",         "role": "intermediate", "kind": "set",    "shape": "3",            "desc": "encoder, embedding-norm and decoder AdamW parameter groups",           "sample": ["ae_encoder", "ae_embedding_norm", "ae_decoder"]},
            {"id": "eta",    "tex": r"\eta_{\mathrm{eff}}",       "role": "intermediate", "kind": "vector", "shape": "3",            "desc": "per-group effective LR (base x cosine x warmup)",                      "sample": ["2.7e-4", "2.7e-4", "2.7e-4"]},
            {"id": "gnorm",  "tex": r"\lVert\mathbf{g}\rVert_2",  "role": "intermediate", "kind": "scalar", "shape": "1",            "desc": "global gradient L2 norm",                                              "sample": "1.4"},
            {"id": "w",      "tex": r"\theta_t",                  "role": "intermediate", "kind": "vector", "shape": "|theta|",      "desc": "model weights at optimiser step t",                                    "sample": ["0.31", "-0.08", "..."]},
            {"id": "wbest",  "tex": r"\theta^{\star}",            "role": "final",        "kind": "vector", "shape": "|theta|",      "desc": "best-epoch checkpointed autoencoder weights",                          "sample": ["0.30", "-0.09", "..."]},
        ]
        steps = [
            {
                "id": "pae_stack", "title": "Parameter load and de-interleave", "phase": "A - Curve genesis",
                "note": "The extraction parameter artifact is memory-mapped and cropped to each split's zero-based local slices; the 3K interleaved channels are de-interleaved by stride-3 into per-pixel amplitude, mean and width matrices.",
                "inputs": ["params"], "outputs": ["gp"],
                "lines": [
                    [{"id": "gp", "tex": r"(a,\mu,\sigma)_p", "role": "intermediate"}, {"tex": "="}, {"tex": r"\big("}, {"id": "params", "tex": r"\Theta", "role": "measured"}, {"tex": r"[0{::}3],\ \Theta[1{::}3],\ \Theta[2{::}3]\big)^{\top},\qquad K = C/3"}],
                ],
            },
            {
                "id": "pae_select", "title": "Active-pixel gate and subsample", "phase": "A - Curve genesis",
                "note": "A pixel is active when any component amplitude exceeds amp_zero_thr = 1e-4; active pixels are kept at fraction pixel_subsample (default 1.0) and empty pixels at keep_empty_frac = 0.05, then the union is seed-shuffled.",
                "inputs": ["gp"], "outputs": ["active", "idx"],
                "lines": [
                    [{"id": "active", "tex": r"\mathbb{1}_{\mathrm{act},p}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\bigvee_{k}\big["}, {"id": "gp", "tex": r"a_{p,k}", "role": "intermediate"}, {"tex": r" > \tau_a\big],\qquad \tau_a = 10^{-3}"}],
                    [{"id": "idx", "tex": r"\mathcal{I}", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathrm{shuffle}\big(\mathcal{A}_{\rho}\,\cup\,\mathcal{E}_{\phi}\big),\quad |\mathcal{A}_\rho| = \rho\,|\mathcal{A}|,\ \ |\mathcal{E}_\phi| = 0.05\,|\mathcal{E}|"}],
                ],
            },
            {
                "id": "pae_genesis", "title": "Gaussian curve genesis", "phase": "A - Curve genesis",
                "note": "For each kept pixel the elevation profile is synthesised on the fly by summing the K Gaussians over the axis; the width is floored at 1e-6 and the exponent clipped to [-100, 0] before exponentiation. Once normalised, this curve is the reconstruction target; the encoder input additionally carries the optional noise.",
                "inputs": ["gp", "idx"], "outputs": ["curve"],
                "lines": [
                    [{"id": "curve", "tex": r"c_h", "role": "calculated"}, {"tex": "="}, {"tex": r"\sum_{k}"}, {"id": "gp", "tex": r"a_k", "role": "intermediate"}, {"tex": r"\exp\!\Big(\mathrm{clip}\big(-\tfrac{(x_h-\mu_k)^2}{2\max(\sigma_k,10^{-6})^2},\ -100,\ 0\big)\Big)"}],
                ],
            },
            {
                "id": "pae_augment", "title": "Curve augmentation", "phase": "B - Normalization",
                "note": "Train split only. With per-operation probabilities the profile is amplitude-scaled, circularly shifted by up to max_shift bins (np.roll) and axis-flipped; only the flip is on by default (p_flip = 0.5, p_amp_scale = p_shift = 0).",
                "inputs": ["curve"], "outputs": ["caug"],
                "lines": [
                    [{"id": "caug", "tex": r"\mathbf{c}'", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{flip}_{p_f}\!\circ\,\mathrm{roll}_{k,\,p_s}\!\circ\,\mathrm{scale}_{s,\,p_a}\big("}, {"id": "curve", "tex": r"\mathbf{c}", "role": "calculated"}, {"tex": r"\big)"}],
                    [{"tex": r"s\sim\mathcal{U}(0.9, 1.1),\quad k\sim\mathcal{U}\{-4,\dots,4\},\quad p_f = 0.5"}],
                ],
            },
            {
                "id": "pae_fitstats", "title": "Fit log1p-standardize statistics", "phase": "B - Normalization",
                "note": "On the train split only and in float64, the location and scale are the mean and standard deviation of log1p(max(c,0)) over up to 100000 deterministically sampled genesis profiles (seed 42); the scale is floored at 1e-6.",
                "inputs": ["curve"], "outputs": ["stats"],
                "lines": [
                    [{"tex": r"f(\mathbf{c}) = \log\!\big(1 + \max(\mathbf{c},0)\big)"}],
                    [{"id": "stats", "tex": r"(\ell, s)", "role": "calculated"}, {"tex": "="}, {"tex": r"\big(\operatorname{mean} f(\mathbf{c}),\ \max(\operatorname{std} f(\mathbf{c}),\ 10^{-6})\big),\qquad N_{\mathrm{fit}} \le 10^{5}"}],
                ],
            },
            {
                "id": "pae_normalise", "title": "Normalise and jitter", "phase": "B - Normalization",
                "note": "The fitted statistics standardise every split identically; on the train split only, Gaussian noise of std noise_std (default 0.01, in normalised units) is added after normalisation with probability p_noise. The noise perturbs only the encoder input; the reconstruction target stays the clean normalised curve, making the objective a denoising one whenever p_noise > 0.",
                "inputs": ["caug", "stats"], "outputs": ["cn"],
                "lines": [
                    [{"id": "cn", "tex": r"\hat{\mathbf{c}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{f("}, {"id": "caug", "tex": r"\mathbf{c}'", "role": "intermediate"}, {"tex": r") - "}, {"id": "stats", "tex": r"\ell", "role": "calculated"}, {"tex": r"}{"}, {"id": "stats", "tex": r"s", "role": "calculated"}, {"tex": r"}"}],
                    [{"id": "cn", "tex": r"\hat{\mathbf{c}}", "role": "calculated"}, {"tex": r"\leftarrow \hat{\mathbf{c}} + \varepsilon,\quad \varepsilon\sim\mathcal{N}(0,\sigma_N^2),\ \ \sigma_N = 0.01\ \ (\text{train},\ p_N)"}],
                ],
            },
            {
                "id": "pae_encode", "title": "Encode to bottleneck", "phase": "C - Autoencode",
                "note": "The profile vector is mapped by the encoder (default: a 4-layer 1x1-conv MLP, hidden 512, GELU) to a low-dimensional embedding; the bottleneck width is embedding_dim = 24.",
                "inputs": ["cn"], "outputs": ["z"],
                "lines": [
                    [{"id": "z", "tex": r"\mathbf{z}", "role": "intermediate"}, {"tex": "="}, {"tex": r"E_{\phi}\!\big("}, {"id": "cn", "tex": r"\hat{\mathbf{c}}", "role": "calculated"}, {"tex": r"\big),\qquad \mathbf{z}\in\mathbb{R}^{d},\ \ d = 24"}],
                ],
            },
            {
                "id": "pae_embednorm", "title": "Normalise the embedding", "phase": "C - Autoencode",
                "note": "The bottleneck is normalised by the embedding_norm mode; the default layernorm standardises across the d channels with learnable affine (nn.LayerNorm, eps 1e-5), while l2 projects to the unit sphere (eps 1e-6) and none passes through.",
                "inputs": ["z"], "outputs": ["zn"],
                "lines": [
                    [{"id": "zn", "tex": r"\hat{\mathbf{z}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\gamma\odot\dfrac{"}, {"id": "z", "tex": r"\mathbf{z} - \overline{\mathbf{z}}", "role": "intermediate"}, {"tex": r"}{\sqrt{\operatorname{Var}(\mathbf{z}) + 10^{-5}}} + \beta\quad(\texttt{layernorm})"}],
                    [{"tex": r"\texttt{l2}:\ \hat{\mathbf{z}} = \mathbf{z}/\max(\lVert\mathbf{z}\rVert_2,\,10^{-6}),\qquad \texttt{none}:\ \hat{\mathbf{z}} = \mathbf{z}"}],
                ],
            },
            {
                "id": "pae_decode", "title": "Decode to profile", "phase": "C - Autoencode",
                "note": "The decoder mirrors the encoder, projecting the normalised embedding back to a full-length profile; the output has no final activation, so the reconstruction lives in the same normalised space as the target.",
                "inputs": ["zn"], "outputs": ["crec"],
                "lines": [
                    [{"id": "crec", "tex": r"\tilde{\mathbf{c}}", "role": "calculated"}, {"tex": "="}, {"tex": r"D_{\psi}\!\big("}, {"id": "zn", "tex": r"\hat{\mathbf{z}}", "role": "calculated"}, {"tex": r"\big),\qquad \tilde{\mathbf{c}}\in\mathbb{R}^{L}"}],
                ],
            },
            {
                "id": "pae_recon", "title": "Reconstruction loss", "phase": "D - Loss",
                "note": "The total is a weighted sum of the enabled use_*_curve terms, each scaled by its weight_*: pointwise MSE, L1, Huber (bends at huber_delta) and Charbonnier (smoothed with charbonnier_eps) on the residual, cosine shape agreement and the log energy-ratio along the height axis, TV as the mean absolute first height-difference of the residual, and Sobolev as the MSE of its second height-difference. The default enables only MSE at weight 1; use_latent_noise additionally decodes the embedding perturbed with N(0, latent_noise_std^2) noise against the same clean target (weight weight_latent_noise), training the decoder to stay smooth off the encoder manifold.",
                "inputs": ["crec", "cn"], "outputs": ["err", "loss"],
                "lines": [
                    [{"id": "err", "tex": r"e", "role": "intermediate"}, {"tex": "="}, {"id": "crec", "tex": r"\tilde{\mathbf{c}}", "role": "calculated"}, {"tex": r"\ -\ "}, {"id": "cn", "tex": r"\hat{\mathbf{c}}", "role": "calculated"}],
                    [{"id": "loss", "tex": r"\mathcal{L}", "role": "calculated"}, {"tex": "="}, {"tex": r"\big\langle e^2\big\rangle\ (\texttt{mse}),\ \ \big\langle|e|\big\rangle\ (\texttt{l1}),\ \ \mathrm{Huber}_{\delta=1},\ \ \big\langle\sqrt{e^2+\epsilon^2}\big\rangle_{\epsilon=10^{-3}}"}],
                ],
            },
            {
                "id": "pae_paramgroups", "title": "Encoder, embedding-norm and decoder groups", "phase": "E - Optimiser step",
                "note": "AdamW holds three parameter groups: encoder, the embedding LayerNorm affine (at the encoder rate and decay, present only while embedding_norm is layernorm) and decoder, each with its own learning rate and weight decay (defaults 3e-4 and 1e-4); shared betas (0.9, 0.999) and eps 1e-8. Empty groups are dropped, and get_param_groups raises if any model parameter falls outside the groups.",
                "inputs": [], "outputs": ["groups"],
                "lines": [
                    [{"id": "groups", "tex": r"g_{\mathrm{enc}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\{E_\phi;\ \eta_e,\ \lambda_e\},\qquad"}, {"id": "groups", "tex": r"g_{\mathrm{norm}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\{\gamma,\beta;\ \eta_e,\ \lambda_e\},\qquad"}, {"id": "groups", "tex": r"g_{\mathrm{dec}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\{D_\psi;\ \eta_d,\ \lambda_d\}"}],
                    [{"tex": r"\eta_e = \eta_d = 3\times10^{-4},\quad \lambda_e = \lambda_d = 10^{-4},\quad (\beta_1,\beta_2) = (0.9, 0.999),\ \epsilon = 10^{-8}"}],
                ],
            },
            {
                "id": "pae_schedule", "title": "Warmup and cosine schedule", "phase": "E - Optimiser step",
                "note": "Each group's effective LR is its base rate times the cosine-annealing factor toward eta_min = 1e-6 over the epoch horizon T = scheduler.epochs, which the entry point resolves to training.epochs = 60, times a linear warmup ramping from warmup_start_factor = 0.1 over warmup_steps = 200 optimiser steps.",
                "inputs": ["groups"], "outputs": ["eta"],
                "lines": [
                    [{"tex": r"F(t) = \tfrac{\eta_{\min}}{\eta_0} + \tfrac12\big(1 - \tfrac{\eta_{\min}}{\eta_0}\big)\big(1 + \cos\tfrac{\pi\min(t,T)}{T}\big),\quad \eta_{\min} = 10^{-6},\ T = 60"}],
                    [{"id": "eta", "tex": r"\eta_{\mathrm{eff}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\eta_0\,F(t)\,f_{\mathrm{w}}(s),\qquad f_{\mathrm{w}}(s) = \alpha_0 + (1-\alpha_0)\tfrac{s}{S},\ \ \alpha_0 = 0.1,\ S = 200"}],
                ],
            },
            {
                "id": "pae_gradstep", "title": "Grad clip and AdamW update", "phase": "E - Optimiser step",
                "note": "After a finiteness guard the global gradient norm is clipped to max_grad_norm = 1.0 (fixed mode), then AdamW applies bias-corrected moments with decoupled weight decay; the epoch loop drives the reconstruction loss down.",
                "inputs": ["loss", "eta"], "outputs": ["gnorm", "w"],
                "iterative": {"var": "loss", "steps": 60, "unit": "epoch", "symbol": "L",
                              "trace": ["6.4e-2", "4.0e-2", "2.9e-2", "2.1e-2", "1.6e-2", "1.3e-2"]},
                "lines": [
                    [{"id": "gnorm", "tex": r"\lVert\mathbf{g}\rVert_2", "role": "intermediate"}, {"tex": "="}, {"tex": r"\Big(\textstyle\sum_i\lVert\nabla_{\theta^{(i)}}"}, {"id": "loss", "tex": r"\mathcal{L}", "role": "calculated"}, {"tex": r"\rVert_2^2\Big)^{1/2},\quad \mathbf{g}\leftarrow\mathbf{g}\,\min\!\big(1,\ \tfrac{\tau}{\lVert\mathbf{g}\rVert_2 + \epsilon}\big),\ \tau = 1"}],
                    [{"id": "w", "tex": r"\theta_{t+1}", "role": "intermediate"}, {"tex": "="}, {"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": r"\ -\ "}, {"id": "eta", "tex": r"\eta_{\mathrm{eff}}", "role": "intermediate"}, {"tex": r"\Big(\tfrac{\hat m_t}{\sqrt{\hat v_t}+\epsilon} + \lambda\,\theta_t\Big)"}],
                ],
            },
            {
                "id": "pae_checkpoint", "title": "Validation and checkpoint", "phase": "E - Optimiser step",
                "note": "Every validation_frequency epochs, which the entry point sets to 1, the model (under EMA when enabled) is evaluated; the best epoch is checkpointed on strict improvement and early stopping restores it after early_stop_patience = 30 evaluations without a new minimum.",
                "inputs": ["w"], "outputs": ["wbest"],
                "lines": [
                    [{"id": "wbest", "tex": r"\theta^{\star}", "role": "final"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,min}_{t}\ \mathcal{L}_{\mathrm{val}}\!\big("}, {"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": r"\big),\qquad \mathrm{patience} = 30\ \text{evals}"}],
                ],
            },
        ]
        return {
            "key": "profile_ae_train", "name": "Profile AE (Train)",
            "blurb": "A profile autoencoder trained to reconstruct elevation curves. Synthesise each pixel's curve from its Gaussian mixture parameters, augment and log1p-standardise it, compress to a normalised bottleneck embedding and decode it back, then minimise a single reconstruction loss with AdamW, warmup, cosine annealing and early stopping.",
            "nodes": nodes, "steps": steps,
        }

    def _image_ae_train(self) -> dict:
        """Returns the flow for training the 2D image autoencoder on input patches."""
        nodes = [
            {"id": "x",     "tex": r"\mathbf{x}",               "role": "measured",     "kind": "tensor", "shape": "B x C_in x P x P",  "desc": "normalised input patch batch; also the reconstruction target", "sample": [["0.41", "-0.20"], ["-0.33", "0.27"]]},
            {"id": "zpre",  "tex": r"\mathbf{z}_0",             "role": "intermediate", "kind": "tensor", "shape": "B x C_e x P' x P'", "desc": "raw encoder embedding before latent normalisation",            "sample": [["0.82", "-1.20"], ["0.31", "0.54"]]},
            {"id": "z",     "tex": r"\mathbf{z}",               "role": "calculated",   "kind": "tensor", "shape": "B x C_e x P' x P'", "desc": "normalised latent code (bottleneck)",                          "sample": [["0.44", "-0.64"], ["0.17", "0.29"]]},
            {"id": "xhat",  "tex": r"\hat{\mathbf{x}}",         "role": "calculated",   "kind": "tensor", "shape": "B x C_in x P x P",  "desc": "decoder reconstruction of the input patch",                    "sample": [["0.39", "-0.18"], ["-0.30", "0.29"]]},
            {"id": "e",     "tex": r"\mathbf{e}",               "role": "intermediate", "kind": "tensor", "shape": "B x C_in x P x P",  "desc": "reconstruction residual x-hat minus x",                        "sample": ["-0.02", "0.02", "0.03", "..."]},
            {"id": "lrec",  "tex": r"\ell",                     "role": "calculated",   "kind": "scalar", "shape": "1",                 "desc": "reconstruction loss (single component image_recon)",           "sample": "1.8e-2"},
            {"id": "gnorm", "tex": r"\lVert\mathbf{g}\rVert_2", "role": "intermediate", "kind": "scalar", "shape": "1",                 "desc": "global gradient L2 norm",                                      "sample": "0.83"},
            {"id": "grad",  "tex": r"\mathbf{g}",               "role": "intermediate", "kind": "vector", "shape": "|theta|",           "desc": "clipped parameter gradient",                                   "sample": ["1.2e-2", "-4e-3", "..."]},
            {"id": "eta",   "tex": r"\eta_{\mathrm{eff}}",      "role": "intermediate", "kind": "scalar", "shape": "1",                 "desc": "effective LR (base x cosine x warmup)",                        "sample": "2.9e-4"},
            {"id": "w",     "tex": r"\theta_t",                 "role": "intermediate", "kind": "vector", "shape": "|theta|",           "desc": "encoder/decoder weights at optimiser step t",                  "sample": ["0.31", "-0.08", "..."]},
            {"id": "wbest", "tex": r"\theta^{\star}",           "role": "final",        "kind": "vector", "shape": "|theta|",           "desc": "best-epoch checkpointed weights",                              "sample": ["0.30", "-0.09", "..."]},
        ]
        steps = [
            {
                "id": "iae_encode", "title": "Encoder downsampling", "phase": "A - Encode",
                "note": "The stem lifts the C_in-channel patch to base_channels (32); n = log2(downsample_factor) strided stages each halve resolution and double width; a 1x1 head projects to the embedding_dim (24) latent map.",
                "inputs": ["x"], "outputs": ["zpre"],
                "lines": [
                    [{"id": "zpre", "tex": r"\mathbf{z}_0", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{emb}_{1\times1}\!\big(\mathrm{down}^{(n)}\!\big(\mathrm{stem}\big("}, {"id": "x", "tex": r"\mathbf{x}", "role": "measured"}, {"tex": r"\big)\big)\big)"}],
                    [{"tex": r"n = \log_2 s_{\mathrm{ds}},\qquad C_e = d_{\mathrm{emb}} = 24,\qquad P' = P / s_{\mathrm{ds}}\ \ (s_{\mathrm{ds}} = 1\ \text{for conv2d})"}],
                ],
            },
            {
                "id": "iae_embednorm", "title": "Embedding normalisation", "phase": "A - Encode",
                "note": "The latent map is normalised by the configured mode (default none): l2 rescales each pixel's channel vector to unit length with a 1e-6 floor, layernorm standardises across channels per pixel with a 1e-6 variance floor.",
                "inputs": ["zpre"], "outputs": ["z"],
                "lines": [
                    [{"id": "z", "tex": r"\mathbf{z}", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{"}, {"id": "zpre", "tex": r"\mathbf{z}_0", "role": "intermediate"}, {"tex": r"}{\max\!\big(\lVert\mathbf{z}_0\rVert_2,\ \epsilon\big)}\ \ (\texttt{l2}),\qquad \epsilon = 10^{-6},\ \ \lVert\cdot\rVert_2\ \text{over channels}"}],
                    [{"tex": r"\mathbf{z} = \dfrac{\mathbf{z}_0 - \mu_c}{\sqrt{\sigma_c^2 + 10^{-6}}}\ \ (\texttt{layernorm}),\qquad \mathbf{z} = \mathbf{z}_0\ \ (\texttt{none})"}],
                ],
            },
            {
                "id": "iae_decode", "title": "Decoder reconstruction", "phase": "B - Decode",
                "note": "A 1x1 layer lifts the latent back to the bottleneck width; n upsampling stages each double resolution and halve width (convtranspose by default); depth-1 refinement blocks follow, and a 1x1 head returns the C_in-channel patch.",
                "inputs": ["z"], "outputs": ["xhat"],
                "lines": [
                    [{"id": "xhat", "tex": r"\hat{\mathbf{x}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathrm{head}_{1\times1}\!\big(\mathrm{refine}\big(\mathrm{up}^{(n)}\!\big(\mathrm{emb}^{-1}_{1\times1}\big("}, {"id": "z", "tex": r"\mathbf{z}", "role": "calculated"}, {"tex": r"\big)\big)\big)\big)\ \in\ \mathbb{R}^{C_{\mathrm{in}}\times P\times P}"}],
                ],
            },
            {
                "id": "iae_residual", "title": "Reconstruction residual", "phase": "Reconstruction loss",
                "note": "The autoencoder is self-supervised: the target is the input patch itself, so the residual is the reconstruction minus the input, shared by all four reconstruction kinds.",
                "inputs": ["xhat", "x"], "outputs": ["e"],
                "lines": [
                    [{"id": "e", "tex": r"\mathbf{e}", "role": "intermediate"}, {"tex": "="}, {"id": "xhat", "tex": r"\hat{\mathbf{x}}", "role": "calculated"}, {"tex": r"\ -\ "}, {"id": "x", "tex": r"\mathbf{x}", "role": "measured"}],
                ],
            },
            {
                "id": "iae_reconterm", "title": "Reconstruction loss term", "phase": "Reconstruction loss",
                "note": "The single loss component image_recon reduces the residual by the configured recon_kind (default mse); Huber bends at delta = 1.0 and Charbonnier smooths the L1 with eps = 1e-3, floored at eps squared.",
                "inputs": ["e"], "outputs": ["lrec"],
                "lines": [
                    [{"tex": r"\ell_{\mathrm{MSE}} = \big\langle \mathbf{e}^2\big\rangle,\qquad \ell_{L1} = \big\langle |\mathbf{e}| \big\rangle"}],
                    [{"id": "lrec", "tex": r"\ell_{\mathrm{Hub}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\big\langle \tfrac12 \mathbf{e}^2\,[|\mathbf{e}|\le\delta] + \delta\big(|\mathbf{e}|-\tfrac{\delta}{2}\big)\,[|\mathbf{e}|>\delta]\big\rangle,\quad \delta = 1"}],
                    [{"tex": r"\ell_{\mathrm{Charb}} = \big\langle \sqrt{\mathbf{e}^2 + \varepsilon^2}\big\rangle,\quad \varepsilon = 10^{-3}"}],
                ],
            },
            {
                "id": "iae_gradclip", "title": "Backprop and gradient clipping", "phase": "Optimiser step",
                "note": "After a per-batch finiteness guard, the global gradient L2 norm is formed and all gradients are rescaled by a common factor so the norm never exceeds the fixed threshold tau = 1.0; the floor epsilon = 1e-6 keeps the scale finite.",
                "inputs": ["lrec"], "outputs": ["gnorm", "grad"],
                "lines": [
                    [{"id": "gnorm", "tex": r"\lVert\mathbf{g}\rVert_2", "role": "intermediate"}, {"tex": "="}, {"tex": r"\Big(\textstyle\sum_i \big\lVert\nabla_{\theta^{(i)}}"}, {"id": "lrec", "tex": r"\ell", "role": "calculated"}, {"tex": r"\big\rVert_2^2\Big)^{1/2}"}],
                    [{"id": "grad", "tex": r"\mathbf{g}", "role": "intermediate"}, {"tex": r"\leftarrow \mathbf{g}\cdot\min\!\Big(1,\ \tfrac{\tau}{\lVert\mathbf{g}\rVert_2 + \varepsilon}\Big),\quad \tau = 1,\ \ \varepsilon = 10^{-6}"}],
                ],
            },
            {
                "id": "iae_adamw", "title": "AdamW update", "phase": "Optimiser step",
                "note": "Two parameter groups, encoder and decoder, each at lr = 3e-4 with decoupled weight decay 1e-4; bias-corrected adaptive moments use betas (0.9, 0.999) and eps 1e-8. The epoch loop drives the reconstruction loss down.",
                "inputs": ["grad", "eta"], "outputs": ["w"],
                "iterative": {"var": "lrec", "steps": 60, "unit": "epoch", "symbol": "L",
                              "trace": ["4.8e-2", "3.1e-2", "2.4e-2", "2.0e-2", "1.8e-2"]},
                "lines": [
                    [{"tex": r"\hat m_t = \tfrac{m_t}{1-\beta_1^t},\quad \hat v_t = \tfrac{v_t}{1-\beta_2^t},\quad (\beta_1,\beta_2) = (0.9,\,0.999)"}],
                    [{"id": "w", "tex": r"\theta_{t+1}", "role": "intermediate"}, {"tex": "="}, {"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": r"\ -\ "}, {"id": "eta", "tex": r"\eta_{\mathrm{eff}}", "role": "intermediate"}, {"tex": r"\Big(\tfrac{\hat m_t}{\sqrt{\hat v_t}+\epsilon} + \lambda\theta_t\Big),\quad \lambda = 10^{-4},\ \epsilon = 10^{-8}"}],
                ],
            },
            {
                "id": "iae_schedule", "title": "Warmup and cosine schedule", "phase": "Schedule & checkpoint",
                "note": "Each group's effective LR is its base rate times the per-epoch cosine factor (T = scheduler.epochs, resolved by the entry point to training.epochs = 60, eta_min = 1e-6) times the per-step linear warmup factor (200 steps, start factor 0.1).",
                "inputs": [], "outputs": ["eta"],
                "lines": [
                    [{"tex": r"F(t) = \tfrac{\eta_{\min}}{\eta_0} + \tfrac12\big(1 - \tfrac{\eta_{\min}}{\eta_0}\big)\big(1 + \cos\tfrac{\pi\min(t,T)}{T}\big),\quad T = 60,\ \eta_{\min} = 10^{-6}"}],
                    [{"id": "eta", "tex": r"\eta_{\mathrm{eff}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\eta_0\cdot F(t)\cdot f_{\mathrm{w}}(s),\qquad f_{\mathrm{w}}(s) = \alpha_0 + (1-\alpha_0)\tfrac{s}{S},\ \ \alpha_0 = 0.1,\ S = 200"}],
                ],
            },
            {
                "id": "iae_checkpoint", "title": "Validation and checkpoint", "phase": "Schedule & checkpoint",
                "note": "Evaluation runs every epoch at the entry-point default validation_frequency = 1; the best epoch is checkpointed on strict improvement of the validation reconstruction loss, and after early_stop_patience = 30 evaluations without a new minimum early stopping restores the best weights.",
                "inputs": ["w"], "outputs": ["wbest"],
                "lines": [
                    [{"id": "wbest", "tex": r"\theta^{\star}", "role": "final"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,min}_{t}\ \mathcal{L}_{\mathrm{val}}\!\big("}, {"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": r"\big),\qquad \text{eval every } 1,\ \ \mathrm{patience} = 30"}],
                ],
            },
        ]
        return {
            "key": "image_ae_train", "name": "Image AE (Train)",
            "blurb": "A 2D convolutional (or ConvNeXt / ViT) autoencoder reconstructs its own normalised input patch: the encoder downsamples to a normalised latent code, the decoder rebuilds the patch, and a single reconstruction loss is backpropagated through two-group AdamW with gradient clipping, warmup, cosine annealing, and best-val checkpointing.",
            "nodes": nodes, "steps": steps,
        }

    def _jepa_train(self) -> dict:
        """Returns the flow for JEPA latent training against a pretrained profile encoder."""
        nodes = [
            {"id": "img",     "tex": r"\mathbf{x}",               "role": "measured",     "kind": "tensor", "shape": "B x C_in x P x P", "desc": "normalised input patch batch from the loader",      "sample": [["0.41", "-0.20"], ["-0.33", "0.27"]]},
            {"id": "gtp",     "tex": r"\theta^{\mathrm{GT}}_{n}", "role": "measured",     "kind": "tensor", "shape": "B x 3K x P x P",   "desc": "loader-normalised GT Gaussian parameters",          "sample": ["0.55", "0.47", "0.34", "..."]},
            {"id": "zhat",    "tex": r"\hat{\mathbf{z}}",         "role": "calculated",   "kind": "tensor", "shape": "B x E x P x P",    "desc": "predicted per-pixel embedding, E = embedding_dim",  "sample": ["0.18", "-0.44", "0.29", "..."]},
            {"id": "gtphys",  "tex": r"\theta^{\mathrm{GT}}",     "role": "intermediate", "kind": "tensor", "shape": "B x 3K x P x P",   "desc": "denormalised physical GT parameters (no_grad)",     "sample": ["12.4", "8.1", "1.9", "..."]},
            {"id": "gtcurve", "tex": r"\gamma",                   "role": "intermediate", "kind": "tensor", "shape": "B x L x P x P",    "desc": "reconstructed GT elevation curve (mixture)",        "sample": [["0.06", "0.70"], ["0.35", "0.86"]]},
            {"id": "gtcn",    "tex": r"\bar{\gamma}",             "role": "intermediate", "kind": "tensor", "shape": "B x L x P x P",    "desc": "profile-normalised GT curve (log1p, standardise)",  "sample": [["-0.9", "0.4"], ["-0.2", "0.8"]]},
            {"id": "zstar",   "tex": r"\mathbf{z}^{\star}",       "role": "calculated",   "kind": "tensor", "shape": "B x E x P x P",    "desc": "target embedding from the profile encoder",         "sample": ["0.20", "-0.41", "0.27", "..."]},
            {"id": "zhn",     "tex": r"\hat{\mathbf{z}}_{n}",     "role": "intermediate", "kind": "tensor", "shape": "B x E x P x P",    "desc": "embedding-normalised prediction",                   "sample": ["0.31", "-0.52", "0.10", "..."]},
            {"id": "zsn",     "tex": r"\mathbf{z}^{\star}_{n}",   "role": "intermediate", "kind": "tensor", "shape": "B x E x P x P",    "desc": "embedding-normalised target",                       "sample": ["0.33", "-0.49", "0.12", "..."]},
            {"id": "chat",    "tex": r"\hat{\gamma}",             "role": "intermediate", "kind": "tensor", "shape": "B x L x P x P",    "desc": "curve decoded from the normalised prediction",      "sample": [["0.05", "0.69"], ["0.34", "0.85"]]},
            {"id": "Lemb",    "tex": r"\ell_{\mathrm{emb}}",      "role": "calculated",   "kind": "scalar", "shape": "1",                "desc": "embedding-match loss (weighted enabled terms)",     "sample": "3.2e-2"},
            {"id": "Lrec",    "tex": r"\ell_{\mathrm{rec}}",      "role": "calculated",   "kind": "scalar", "shape": "1",                "desc": "curve-reconstruction anchor loss",                  "sample": "1.7e-2"},
            {"id": "Ltot",    "tex": r"\mathcal{L}",              "role": "final",        "kind": "scalar", "shape": "1",                "desc": "total JEPA loss (plain weighted sum)",              "sample": "4.9e-2"},
            {"id": "w",       "tex": r"\theta_t",                 "role": "intermediate", "kind": "vector", "shape": "|theta|",          "desc": "trainable weights: backbone + finetuned AE groups", "sample": ["0.31", "-0.08", "..."]},
            {"id": "wbest",   "tex": r"\theta^{\star}",           "role": "final",        "kind": "vector", "shape": "|theta|",          "desc": "best-epoch checkpointed weights",                   "sample": ["0.30", "-0.09", "..."]},
            {"id": "diag",    "tex": r"\mathcal{D}",              "role": "final",        "kind": "set",    "shape": "4",                "desc": "inference embedding diagnostics (4 scalars)",       "sample": "MSE=6e-3, cos=0.98"},
        ]
        steps = [
            {
                "id": "jep_couple", "title": "Couple pretrained autoencoder", "phase": "A - Couple",
                "note": "The profile autoencoder is imported from a pretrained run and coupled to the backbone; frozen mode disables its gradients and sets eval, finetune opens a separate optimiser group. Joint training from scratch is rejected, and a live target requires a trainable profile AE plus the curve anchor.",
                "inputs": [], "outputs": ["w"],
                "lines": [
                    [{"tex": r"(E_\phi, D_\phi) \leftarrow \text{pretrained profile AE},\qquad \mathrm{grad}(\phi) = \big[\texttt{mode}=\texttt{finetune}\big]"}],
                    [{"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": "="}, {"tex": r"\theta_{\mathrm{bb}}\ \cup\ \theta^{\mathrm{ft}}_{\mathrm{AE}},\qquad \texttt{mode}\in\{\texttt{frozen},\ \texttt{finetune}\}"}],
                ],
            },
            {
                "id": "jep_predict", "title": "Predict latent embedding", "phase": "A - Couple",
                "note": "One forward pass maps the normalised input patch to a per-pixel latent embedding of width E = embedding_dim (24 by default). When an image autoencoder is coupled it first encodes the input to latent features the backbone consumes; otherwise the backbone reads the dataset channels directly.",
                "inputs": ["img"], "outputs": ["zhat"],
                "lines": [
                    [{"id": "zhat", "tex": r"\hat{\mathbf{z}}", "role": "calculated"}, {"tex": "="}, {"tex": r"f_\theta(\mathbf{u}),\qquad \mathbf{u} = E^{\mathrm{img}}_\psi\big("}, {"id": "img", "tex": r"\mathbf{x}", "role": "measured"}, {"tex": r"\big)\ \text{or}\ "}, {"id": "img", "tex": r"\mathbf{x}", "role": "measured"}],
                    [{"tex": r"\dim_c \hat{\mathbf{z}} = E = \dim_{\mathrm{emb}}\quad (\text{default } 24)"}],
                ],
            },
            {
                "id": "jep_gtcurve", "title": "Reconstruct and normalise the GT curve", "phase": "B - Target",
                "note": "Under no_grad the GT parameters are denormalised to physical units and evaluated on the elevation axis as an additive Gaussian mixture (sigma floored at 1e-6, exponent clamped to [-100, 0]); the curve is then mapped to the autoencoder's own space by log1p compression and standardisation with the pretrained profile stats (scale floored at 1e-6).",
                "inputs": ["gtp"], "outputs": ["gtphys", "gtcurve", "gtcn"],
                "lines": [
                    [{"id": "gtphys", "tex": r"\theta^{\mathrm{GT}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{denorm}\big("}, {"id": "gtp", "tex": r"\theta^{\mathrm{GT}}_{n}", "role": "measured"}, {"tex": r"\big),\qquad "}, {"id": "gtcurve", "tex": r"\gamma", "role": "intermediate"}, {"tex": r"(\xi_n) = \sum_k a_k \exp\!\Big(-\tfrac{(\xi_n-\mu_k)^2}{2\sigma_k^2}\Big)"}],
                    [{"id": "gtcn", "tex": r"\bar{\gamma}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\dfrac{\log(1+\max("}, {"id": "gtcurve", "tex": r"\gamma", "role": "intermediate"}, {"tex": r",0)) - \ell_\gamma}{s_\gamma},\qquad s_\gamma \ge 10^{-6}"}],
                ],
            },
            {
                "id": "jep_target", "title": "Target embedding", "phase": "B - Target",
                "note": "The target embedding is the profile encoder applied to the normalised GT curve. The default stopgrad detaches it (no_grad); live keeps it differentiable through the encoder (requires finetune and the curve anchor to avoid a collapsed constant embedding).",
                "inputs": ["gtcn"], "outputs": ["zstar"],
                "lines": [
                    [{"id": "zstar", "tex": r"\mathbf{z}^{\star}", "role": "calculated"}, {"tex": "="}, {"tex": r"E_\phi\big("}, {"id": "gtcn", "tex": r"\bar{\gamma}", "role": "intermediate"}, {"tex": r"\big)"}],
                    [{"tex": r"\texttt{stopgrad}:\ \mathrm{sg}[\mathbf{z}^{\star}];\quad \texttt{live}:\ \partial\mathbf{z}^{\star}/\partial\phi\ \text{kept}"}],
                ],
            },
            {
                "id": "jep_embednorm", "title": "Embedding normalisation", "phase": "B - Target",
                "note": "Predicted and target embeddings pass through the autoencoder's embedding normalisation before matching. The default layernorm centres each pixel's E-vector, scales it to unit variance (eps 1e-5) and applies a learnable per-channel affine; l2 projects it to the unit sphere (norm floored at 1e-6); none is the identity. Both branches use the identical map so the loss compares them on the same footing.",
                "inputs": ["zhat", "zstar"], "outputs": ["zhn", "zsn"],
                "lines": [
                    [{"id": "zhn", "tex": r"\hat{\mathbf{z}}_{n}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{EN}\big("}, {"id": "zhat", "tex": r"\hat{\mathbf{z}}", "role": "calculated"}, {"tex": r"\big),\qquad "}, {"id": "zsn", "tex": r"\mathbf{z}^{\star}_{n}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{EN}\big("}, {"id": "zstar", "tex": r"\mathbf{z}^{\star}", "role": "calculated"}, {"tex": r"\big)"}],
                    [{"tex": r"\mathrm{EN}(\mathbf{z}) = \gamma\,\tfrac{\mathbf{z}-\mu_z}{\sqrt{\sigma_z^2+10^{-5}}}+\beta\,[\texttt{layernorm}],\ \ \tfrac{\mathbf{z}}{\max(\lVert\mathbf{z}\rVert_2,\,10^{-6})}\,[\texttt{l2}],\ \ \mathbf{z}\,[\texttt{none}]"}],
                ],
            },
            {
                "id": "jep_embloss", "title": "Embedding-match term", "phase": "C - Match",
                "note": "The match term is a mean-squared error between the normalised embeddings by default (weight 1). Optional terms, all off by default, are weighted and summed on top: cosine distance (averaged over pixels whose target norm exceeds 1e-3, similarity clamped to [-1,1]), smooth-L1 (beta 1), Huber (embedding_huber_delta) and Charbonnier (embedding_charbonnier_eps) on the embedding residual, plus two collapse regularizers on the prediction alone: a variance hinge holding each dimension's batch-wide standard deviation above variance_gamma, and a VICReg-style penalty on the squared off-diagonal covariance divided by the embedding dimension.",
                "inputs": ["zhn", "zsn"], "outputs": ["Lemb"],
                "lines": [
                    [{"id": "Lemb", "tex": r"\ell_{\mathrm{emb}}", "role": "calculated"}, {"tex": "="}, {"tex": r"w_{\mathrm{mse}}\big\langle("}, {"id": "zhn", "tex": r"\hat{\mathbf{z}}_{n}", "role": "intermediate"}, {"tex": "-"}, {"id": "zsn", "tex": r"\mathbf{z}^{\star}_{n}", "role": "intermediate"}, {"tex": r")^2\big\rangle + w_{\cos}\ell_{\cos} + w_{\mathrm{sL1}}\ell_{\mathrm{sL1}}"}],
                    [{"tex": r"\ell_{\cos} = \big\langle 1 - \tfrac{\langle\hat{\mathbf{z}}_{n},\mathbf{z}^{\star}_{n}\rangle}{\lVert\hat{\mathbf{z}}_{n}\rVert\,\lVert\mathbf{z}^{\star}_{n}\rVert}\big\rangle_{\lVert\mathbf{z}^{\star}_{n}\rVert>10^{-3}},\qquad (w_{\mathrm{mse}},w_{\cos},w_{\mathrm{sL1}})=(1,0,0)"}],
                ],
            },
            {
                "id": "jep_recon", "title": "Curve-reconstruction anchor", "phase": "C - Match",
                "note": "The anchor decodes the normalised prediction and compares it to the normalised GT curve, keeping the embedding grounded in real profile shape and preventing collapse (mandatory when the target is live). The default reduction is MSE; l1, Huber (delta 1) and Charbonnier (eps 1e-3) are alternatives; weight 1. use_curve_sobolev adds a weighted MSE of the residual's second height-difference, penalising high-frequency jitter in the decoded curve.",
                "inputs": ["zhn", "gtcn"], "outputs": ["chat", "Lrec"],
                "lines": [
                    [{"id": "chat", "tex": r"\hat{\gamma}", "role": "intermediate"}, {"tex": "="}, {"tex": r"D_\phi\big("}, {"id": "zhn", "tex": r"\hat{\mathbf{z}}_{n}", "role": "intermediate"}, {"tex": r"\big)"}],
                    [{"id": "Lrec", "tex": r"\ell_{\mathrm{rec}}", "role": "calculated"}, {"tex": "="}, {"tex": r"w_{\mathrm{rec}}\big\langle("}, {"id": "chat", "tex": r"\hat{\gamma}", "role": "intermediate"}, {"tex": "-"}, {"id": "gtcn", "tex": r"\bar{\gamma}", "role": "intermediate"}, {"tex": r")^2\big\rangle,\qquad w_{\mathrm{rec}}=1"}],
                ],
            },
            {
                "id": "jep_total", "title": "Total JEPA loss", "phase": "C - Match",
                "note": "The total loss is the plain sum of the enabled weighted terms (no weight normalisation, unlike the backbone composite): the embedding-match contribution plus the curve-reconstruction anchor. The defaults make it a unit-weighted MSE embedding loss plus a unit-weighted MSE curve loss.",
                "inputs": ["Lemb", "Lrec"], "outputs": ["Ltot"],
                "lines": [
                    [{"id": "Ltot", "tex": r"\mathcal{L}", "role": "final"}, {"tex": "="}, {"id": "Lemb", "tex": r"\ell_{\mathrm{emb}}", "role": "calculated"}, {"tex": r"\ +\ "}, {"id": "Lrec", "tex": r"\ell_{\mathrm{rec}}", "role": "calculated"}],
                ],
            },
            {
                "id": "jep_step", "title": "AdamW update", "phase": "D - Optimise",
                "note": "The loss backpropagates into the backbone and, in finetune mode, the coupled autoencoder; AdamW steps all groups with linear warmup, cosine annealing and gradient clipping shared from the base trainer. The autoencoder finetune group carries its own learning rate 3e-5 and weight decay 1e-4; a frozen AE contributes no group.",
                "inputs": ["Ltot"], "outputs": ["w"],
                "iterative": {"var": "loss", "steps": 60, "unit": "epoch", "symbol": "L",
                              "trace": ["4.9e-2", "3.1e-2", "2.2e-2", "1.6e-2", "1.2e-2", "9.4e-3"]},
                "lines": [
                    [{"id": "w", "tex": r"\theta_{t+1}", "role": "intermediate"}, {"tex": "="}, {"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": r"\ -\ \eta_{\mathrm{eff}}\,\mathrm{AdamW}\big(\nabla_\theta"}, {"id": "Ltot", "tex": r"\mathcal{L}", "role": "final"}, {"tex": r"\big)"}],
                    [{"tex": r"\theta = \theta_{\mathrm{bb}} \cup \theta^{\mathrm{ft}}_{\mathrm{AE}},\qquad (\eta_{\mathrm{AE}},\lambda_{\mathrm{AE}}) = (3\times10^{-5},\ 10^{-4})"}],
                ],
            },
            {
                "id": "jep_checkpoint", "title": "Validation and checkpoint", "phase": "E - Eval",
                "note": "Validation drives best-epoch checkpointing on strict improvement and early stopping reverts to the best weights after the patience window; the checkpoint stores the backbone and any finetuned autoencoder together so inference can rebuild the coupled predictor.",
                "inputs": ["w"], "outputs": ["wbest"],
                "lines": [
                    [{"id": "wbest", "tex": r"\theta^{\star}", "role": "final"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,min}_t\ \mathcal{L}_{\mathrm{val}}\big("}, {"id": "w", "tex": r"\theta_t", "role": "intermediate"}, {"tex": r"\big)"}],
                ],
            },
            {
                "id": "jep_diag", "title": "Embedding diagnostics", "phase": "E - Eval",
                "note": "At inference the embedding evaluator accumulates four diagnostics over the scene: embedding MSE and mean cosine between predicted and target embeddings, plus two normalised-curve MSEs, the decoder-only (target embedding through the decoder) and full-chain (predicted embedding through the decoder) errors, isolating autoencoder from predictor quality.",
                "inputs": ["zhn", "zsn"], "outputs": ["diag"],
                "lines": [
                    [{"id": "diag", "tex": r"\mathcal{D}", "role": "final"}, {"tex": r"\supset\ \Big\{\ \mathrm{MSE}_{\mathrm{emb}} = \tfrac{\sum\lVert"}, {"id": "zhn", "tex": r"\hat{\mathbf{z}}_{n}", "role": "intermediate"}, {"tex": "-"}, {"id": "zsn", "tex": r"\mathbf{z}^{\star}_{n}", "role": "intermediate"}, {"tex": r"\rVert^2}{N_z},\quad \overline{\cos}\big(\hat{\mathbf{z}}_{n},\mathbf{z}^{\star}_{n}\big)\ \Big\}"}],
                    [{"tex": r"\mathrm{MSE}_{\mathrm{dec}} = \big\langle (D_\phi(\mathbf{z}^{\star}_{n}) - \bar{\gamma})^2\big\rangle,\qquad \mathrm{MSE}_{\mathrm{chain}} = \big\langle (D_\phi(\hat{\mathbf{z}}_{n}) - \bar{\gamma})^2\big\rangle"}],
                ],
            },
        ]
        return {
            "key": "jepa_train", "name": "JEPA (Latent train)",
            "blurb": "Couple a pretrained profile autoencoder (frozen or fine-tuned) to the backbone, predict a per-pixel latent embedding, and match it to the encoder's embedding of the reconstructed ground-truth curve; an MSE embedding term plus a decoder curve-reconstruction anchor are summed and optimised with AdamW, with inference-time embedding diagnostics.",
            "nodes": nodes, "steps": steps,
        }

    def _unrolled_train(self) -> dict:
        """Returns the flow for training the unrolled proximal-gradient gamma_net."""
        nodes = [
            {"id": "gt",    "tex": r"\Theta",                    "role": "measured",     "kind": "tensor", "shape": "3K x P x P", "desc": "normalised GT Gaussian parameters from the dataset patch",              "sample": [["-0.63", "0.58"], ["0.41", "-0.22"]]},
            {"id": "kz",    "tex": r"K_z",                       "role": "measured",     "kind": "tensor", "shape": "T x P x P",  "desc": "per-pixel interferometric wavenumber map from the geometry field",      "sample": [["-0.14", "-0.05"], ["0.06", "0.15"]]},
            {"id": "gphys", "tex": r"\Theta_{\mathrm{phys}}",    "role": "intermediate", "kind": "tensor", "shape": "3K x P x P", "desc": "denormalised physical parameters (a, mu, sigma)",                       "sample": [["0.81", "12.4", "1.9"], ["0.55", "31.8", "2.6"]]},
            {"id": "s",     "tex": r"\mathbf{s}",                "role": "calculated",   "kind": "tensor", "shape": "N x P x P",  "desc": "power-normalised GT elevation profile: measurement source and target",  "sample": ["0.00", "0.04", "0.13", "0.05", "0.00"]},
            {"id": "y",     "tex": r"\mathbf{y}",                "role": "calculated",   "kind": "tensor", "shape": "T x P x P",  "desc": "synthesised complex coherence per track, optional complex noise added", "sample": ["0.93-0.12j", "0.71+0.30j", "0.42+0.51j"]},
            {"id": "s0",    "tex": r"\mathbf{s}^{0}",            "role": "intermediate", "kind": "tensor", "shape": "N x P x P",  "desc": "matched-filter (beamforming) initialisation",                           "sample": ["0.02", "0.31", "0.94", "0.38", "0.05"]},
            {"id": "r",     "tex": r"\mathbf{r}^{l}",            "role": "intermediate", "kind": "tensor", "shape": "N x P x P",  "desc": "profile after the Lipschitz-normalised gradient step of layer l",       "sample": ["0.01", "0.28", "0.99", "0.35", "0.02"]},
            {"id": "sl",    "tex": r"\mathbf{s}^{L}",            "role": "calculated",   "kind": "tensor", "shape": "N x P x P",  "desc": "final unrolled estimate after L prox-gradient layers",                  "sample": ["0.00", "0.05", "0.12", "0.06", "0.00"]},
            {"id": "mask",  "tex": r"\mathbb{1}_{\mathrm{pow}}", "role": "intermediate", "kind": "tensor", "shape": "P x P",      "desc": "power mask: pixels whose integrated GT profile exceeds the floor",      "sample": ["1", "0", "1", "1"]},
            {"id": "loss",  "tex": r"\mathcal{L}",               "role": "calculated",   "kind": "scalar", "shape": "1",          "desc": "power-masked L1/MSE curve loss over the elevation axis",                "sample": "2.4e-2"},
            {"id": "eta",   "tex": r"\eta_{\mathrm{eff}}",       "role": "intermediate", "kind": "vector", "shape": "2",          "desc": "per-group effective LR: base x cosine x linear warmup (steps, prox)",   "sample": ["9.1e-4", "9.1e-4"]},
            {"id": "ema",   "tex": r"\bar{\theta}",              "role": "intermediate", "kind": "vector", "shape": "|theta|",    "desc": "EMA shadow weights updated after every optimizer step",                 "sample": ["0.42", "-0.11", "..."]},
            {"id": "best",  "tex": r"\theta^{\star}",            "role": "final",        "kind": "vector", "shape": "|theta|",    "desc": "best-validation checkpoint (the EMA weights when use_ema is on)",       "sample": ["0.41", "-0.12", "..."]},
        ]
        steps = [
            {
                "id": "unr_render", "title": "Profile rendering and power normalisation", "phase": "A - Measurement synthesis",
                "note": "The batch GT parameters are denormalised to physical units and rendered to profiles on the elevation grid; each profile is divided by its integrated power so the inversion is scale-free. Pixels below the power floor are masked out of everything downstream.",
                "inputs": ["gt"], "outputs": ["gphys", "s", "mask"],
                "lines": [
                    [{"id": "gphys", "tex": r"\Theta_{\mathrm{phys}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{denorm}\big("}, {"id": "gt", "tex": r"\Theta", "role": "measured"}, {"tex": r"\big),\qquad c_h = \sum_k a_k\,e^{-(x_h-\mu_k)^2/2\sigma_k^2}"}],
                    [{"id": "s", "tex": r"\mathbf{s}", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathbf{c}\,\big/\,\max\!\big(\textstyle\sum_h c_h\,\mathrm{d}z,\ \varepsilon\big),\qquad"}, {"id": "mask", "tex": r"\mathbb{1}_{\mathrm{pow}}", "role": "intermediate"}, {"tex": r"= \big[\textstyle\sum_h c_h\,\mathrm{d}z > \varepsilon\big]"}],
                ],
            },
            {
                "id": "unr_synth", "title": "Coherence synthesis through the exact operator", "phase": "A - Measurement synthesis",
                "note": "The per-pixel steering operator is built from the geometry-field kz map and the elevation axis; pushing the normalised GT profile through it yields the complex coherence vector the network must invert. Optional complex Gaussian noise (measurement_noise_std) breaks the inverse-crime purity.",
                "inputs": ["s", "kz"], "outputs": ["y"],
                "lines": [
                    [{"id": "y", "tex": r"y_t", "role": "calculated"}, {"tex": "="}, {"tex": r"\sum_h"}, {"id": "s", "tex": r"s_h", "role": "calculated"}, {"tex": r"\,e^{\,j\,"}, {"id": "kz", "tex": r"\kappa_{z,t}", "role": "measured"}, {"tex": r"x_h}\,\mathrm{d}z \;+\; \tfrac{\sigma_n}{\sqrt{2}}\,(\epsilon_1 + j\epsilon_2)"}],
                ],
            },
            {
                "id": "unr_init", "title": "Matched-filter initialisation", "phase": "B - Unrolled inversion",
                "note": "gamma_net starts from the beamforming solution: the adjoint of the steering operator applied to the measurements, averaged over tracks and clipped to nonnegative reflectivity.",
                "inputs": ["y", "kz"], "outputs": ["s0"],
                "lines": [
                    [{"id": "s0", "tex": r"\mathbf{s}^{0}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\max\!\Big(0,\ \tfrac{1}{T}\,\mathrm{Re}\big[\mathbf{A}^{H}"}, {"id": "y", "tex": r"\mathbf{y}", "role": "calculated"}, {"tex": r"\big]\Big)"}],
                ],
            },
            {
                "id": "unr_iter", "title": "Learned proximal-gradient layers", "phase": "B - Unrolled inversion",
                "note": "Each of the L layers takes a gradient step on the data fidelity, normalised by the operator's Lipschitz bound T*N*dz^2 so step_init = 1 is stable, refines the profile with a learned per-pixel 1D conv prox along elevation, and applies a nonnegative soft-threshold. Steps and thresholds are softplus-reparameterised per layer.",
                "inputs": ["s0", "y", "kz"], "outputs": ["r", "sl"],
                "lines": [
                    [{"id": "r", "tex": r"\mathbf{r}^{l}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathbf{s}^{l} + \alpha_l\,\frac{\mathrm{Re}\big[\mathbf{A}^{H}(\mathbf{y} - \mathbf{A}\mathbf{s}^{l})\big]}{T\,N\,\mathrm{d}z^{2}}"}],
                    [{"id": "sl", "tex": r"\mathbf{s}^{l+1}", "role": "calculated"}, {"tex": "="}, {"tex": r"\max\!\big(0,\ \mathcal{P}_l("}, {"id": "r", "tex": r"\mathbf{r}^{l}", "role": "intermediate"}, {"tex": r") - \theta_l\big),\qquad l = 0,\dots,L-1"}],
                ],
            },
            {
                "id": "unr_loss", "title": "Power-masked curve loss", "phase": "C - Loss",
                "note": "The reconstruction error is averaged along the elevation axis per pixel, then averaged over pixels that carry GT power; empty pixels contribute nothing. curve_loss selects L1 (default) or MSE.",
                "inputs": ["sl", "s", "mask"], "outputs": ["loss"],
                "lines": [
                    [{"id": "loss", "tex": r"\mathcal{L}", "role": "calculated"}, {"tex": "="}, {"tex": r"\frac{\sum_p \mathbb{1}_{\mathrm{pow},p}\;\tfrac{1}{N}\sum_h \big|"}, {"id": "sl", "tex": r"s^{L}_{p,h}", "role": "calculated"}, {"tex": r" - "}, {"id": "s", "tex": r"s_{p,h}", "role": "calculated"}, {"tex": r"\big|}{\max\big(\sum_p \mathbb{1}_{\mathrm{pow},p},\ 1\big)}"}],
                ],
            },
            {
                "id": "unr_optim", "title": "AdamW step with warmup and cosine schedule", "phase": "D - Optimise",
                "note": "Two parameter groups (steps + thresholds, prox convolutions) with their own LR and weight decay from GammaNetConfig.get_param_groups. Gradients are clipped to max_grad_norm; the effective LR is the cosine-annealed base scaled by the linear warmup factor while warmup is active.",
                "inputs": ["loss"], "outputs": ["eta"],
                "lines": [
                    [{"id": "eta", "tex": r"\eta_{\mathrm{eff}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\eta_{\mathrm{base}}\;\cdot\;\underbrace{\big(\rho + (1-\rho)\,\tfrac{t}{T_w}\big)}_{\mathrm{warmup}}\;\cdot\;\underbrace{\tfrac{1}{2}\big(1 + \cos\pi\tfrac{e}{E}\big)}_{\mathrm{cosine}}"}],
                ],
            },
            {
                "id": "unr_ema", "title": "EMA shadow and averaged evaluation", "phase": "D - Optimise",
                "note": "When use_ema is on, a shadow copy of the weights is blended after every optimizer step, and validation, best-checkpointing and the final test all run with the shadow weights swapped in (WeightEma.applied).",
                "inputs": ["eta"], "outputs": ["ema"],
                "lines": [
                    [{"id": "ema", "tex": r"\bar{\theta}", "role": "intermediate"}, {"tex": r"\leftarrow"}, {"tex": r"\beta\,\bar{\theta} + (1-\beta)\,\theta_t,\qquad \beta = \mathrm{ema\_decay}"}],
                ],
            },
            {
                "id": "unr_ckpt", "title": "Checkpointing, early stop and test", "phase": "D - Optimise",
                "note": "The unrolled family runs the shared BaseTrainer loop: the best validation loss checkpoints best_model.pt (the EMA weights when enabled), a resumable trainer state is written to last.pt every epoch, training stops after early_stop_patience validation rounds without improvement, the best weights are reloaded for the test pass, and the loss history plus test metrics (loss, peak MAE in metres) land in training_summary.json. No TensorBoard events are written because the run carries no writer.",
                "inputs": ["ema", "loss"], "outputs": ["best"],
                "lines": [
                    [{"id": "best", "tex": r"\theta^{\star}", "role": "final"}, {"tex": "="}, {"tex": r"\arg\min_{e}\ \mathcal{L}^{\mathrm{val}}_{e},\qquad \mathrm{stop\ after}\ p\ \mathrm{epochs\ without\ improvement}"}],
                ],
            },
        ]
        return {
            "key": "unrolled_train", "name": "Unrolled Physics (Train)",
            "blurb": "Ground-truth Gaussian profiles are rendered, power-normalised and pushed through the exact per-pixel steering operator to synthesise coherence measurements; gamma_net inverts them with L learned proximal-gradient layers, and a power-masked curve loss is optimised by AdamW with linear warmup, cosine annealing, optional EMA weight averaging and best-epoch checkpointing.",
            "nodes": nodes, "steps": steps,
        }

    def _inference(self) -> dict:
        """Returns the flow for sliding-window backbone inference and cube stitching."""
        nodes = [
            {"id": "ckpt",     "tex": r"\theta^{\star}",             "role": "measured",     "kind": "vector", "shape": "|theta|",           "desc": "best-epoch checkpoint weights (params) with bundled x-axis; per-slot norm stats load from the run meta", "sample": ["0.31", "-0.08", "..."]},
            {"id": "xaxis",    "tex": r"\mathbf{x}",                 "role": "measured",     "kind": "vector", "shape": "N",                 "desc": "elevation axis (m) restored from the checkpoint",                                                        "sample": ["-20", "-19.6", "...", "20"]},
            {"id": "xhat",     "tex": r"\hat{\mathbf{x}}",           "role": "measured",     "kind": "tensor", "shape": "B x C_in x P x P",  "desc": "normalised input patch batch from the loader",                                                           "sample": [["0.41", "-0.20"], ["-0.33", "0.27"]]},
            {"id": "znorm",    "tex": r"\hat{\mathbf{z}}",           "role": "intermediate", "kind": "tensor", "shape": "B x 3K x P x P",    "desc": "raw normalised network output",                                                                          "sample": ["0.22", "-1.1", "0.7", "..."]},
            {"id": "th",       "tex": r"\hat{\theta}",               "role": "calculated",   "kind": "tensor", "shape": "B x 3K x P x P",    "desc": "denormalised, hard-clamped predicted params (a,mu,sig per slot)",                                        "sample": ["0.78", "12.1", "1.9", "..."]},
            {"id": "thgt",     "tex": r"\theta^{\mathrm{GT}}",       "role": "measured",     "kind": "tensor", "shape": "B x 3K x P x P",    "desc": "ground-truth params, denormalised (no clamp)",                                                           "sample": ["0.80", "12.0", "1.8", "..."]},
            {"id": "thgts",    "tex": r"\theta^{\mathrm{GT}}_{\pi}", "role": "intermediate", "kind": "tensor", "shape": "B x 3K x P x P",    "desc": "mu-sorted GT params (active first, inactive at the tail)",                                               "sample": ["0.80", "11.9", "1.8", "..."]},
            {"id": "p",        "tex": r"\mathbf{p}",                 "role": "intermediate", "kind": "tensor", "shape": "N x P x P",         "desc": "per-patch reconstructed elevation spectrum",                                                             "sample": [["0.05", "0.71"], ["0.33", "0.88"]]},
            {"id": "winv",     "tex": r"w_v",                        "role": "intermediate", "kind": "vector", "shape": "P",                 "desc": "1D Hann taper, floored at 1e-3",                                                                         "sample": ["0.10", "0.45", "0.85", "1.00"]},
            {"id": "win",      "tex": r"w",                          "role": "intermediate", "kind": "matrix", "shape": "P x P",             "desc": "separable 2D Hann window, also the patch centrality",                                                    "sample": [["0.10", "0.45"], ["0.45", "1.00"]]},
            {"id": "acc",      "tex": r"A",                          "role": "intermediate", "kind": "tensor", "shape": "N x H_pad x W_pad", "desc": "curve value accumulator",                                                                                "sample": [["1.2", "3.4"], ["0.8", "2.1"]]},
            {"id": "wacc",     "tex": r"W",                          "role": "intermediate", "kind": "matrix", "shape": "H_pad x W_pad",     "desc": "curve weight accumulator",                                                                               "sample": [["0.9", "1.8"], ["1.8", "2.7"]]},
            {"id": "cube",     "tex": r"\hat{C}",                    "role": "final",        "kind": "tensor", "shape": "N x Az x Rg",       "desc": "stitched predicted curve cube (denorm)",                                                                 "sample": [["0.2", "0.9"], ["0.1", "0.7"]]},
            {"id": "cubegt",   "tex": r"C",                          "role": "measured",     "kind": "tensor", "shape": "N x Az x Rg",       "desc": "stitched ground-truth curve cube (denorm)",                                                              "sample": [["0.2", "0.9"], ["0.1", "0.7"]]},
            {"id": "params",   "tex": r"\hat{\Theta}",               "role": "final",        "kind": "tensor", "shape": "3K x Az x Rg",      "desc": "centrality-selected predicted parameter cube",                                                           "sample": ["0.78", "12.1", "1.9", "..."]},
            {"id": "paramsgt", "tex": r"\Theta^{\mathrm{GT}}",       "role": "measured",     "kind": "tensor", "shape": "3K x Az x Rg",      "desc": "GT parameter cube; inactive-slot mu,sigma set to NaN",                                                   "sample": ["0.80", "11.9", "NaN", "..."]},
            {"id": "pr2",      "tex": r"R^2_{a,r}",                  "role": "calculated",   "kind": "matrix", "shape": "Az x Rg",           "desc": "per-pixel R-squared map",                                                                                "sample": [["0.95", "0.88"], ["0.91", "0.97"]]},
            {"id": "r2",       "tex": r"R^2",                        "role": "final",        "kind": "scalar", "shape": "1",                 "desc": "overall reconstruction R-squared",                                                                       "sample": "0.94"},
            {"id": "psnr",     "tex": r"\mathrm{PSNR}",              "role": "calculated",   "kind": "scalar", "shape": "1",                 "desc": "peak signal-to-noise ratio (dB), GT dynamic range",                                                      "sample": "28.4"},
            {"id": "elevr2",   "tex": r"R^2_{\mathrm{elev}}",        "role": "calculated",   "kind": "vector", "shape": "N",                 "desc": "per-elevation-bin R-squared",                                                                            "sample": ["0.91", "0.93", "..."]},
            {"id": "gmu",      "tex": r"\mathrm{MAE}_{\mu}",         "role": "calculated",   "kind": "scalar", "shape": "1",                 "desc": "matched Gaussian mu MAE over matched active pairs",                                                      "sample": "0.42"},
            {"id": "mf1",      "tex": r"F_1",                        "role": "calculated",   "kind": "scalar", "shape": "1",                 "desc": "matched detection F1 within mu tolerance",                                                               "sample": "0.86"},
            {"id": "redc",     "tex": r"\mathbf{r}",                 "role": "calculated",   "kind": "tensor", "shape": "N x Az x Rg",       "desc": "reduced-subset Capon tomogram (re-synthesised)",                                                         "sample": [["0.3", "0.8"], ["0.2", "0.6"]]},
            {"id": "dimp",     "tex": r"\Delta_{a,r}",               "role": "final",        "kind": "matrix", "shape": "Az x Rg",           "desc": "improvement map: reduced minus prediction MSE (unit-area)",                                              "sample": [["0.01", "-0.00"], ["0.02", "0.01"]]},
            {"id": "xpk",      "tex": r"\hat{\mu}^{\mathrm{ex}}",     "role": "intermediate", "kind": "matrix", "shape": "K x Az x Rg",       "desc": "extracted peak positions (prominence-ranked local maxima of the predicted curve)",                       "sample": [["-8.4", "3.1"], ["-7.9", "2.6"]]},
            {"id": "xsig",     "tex": r"\hat{\sigma}^{\mathrm{ex}}",  "role": "intermediate", "kind": "matrix", "shape": "K x Az x Rg",       "desc": "extracted widths from the half-maximum crossing around each peak",                                       "sample": [["2.1", "1.8"], ["2.4", "1.7"]]},
            {"id": "xamp",     "tex": r"\hat{a}^{\mathrm{ex}}",       "role": "calculated",   "kind": "matrix", "shape": "K x Az x Rg",       "desc": "extracted amplitudes from the ridge-regularised non-negative least squares fit",                         "sample": [["1.2", "0.7"], ["1.4", "0.6"]]},
            {"id": "xr2",      "tex": r"R^2_{\mathrm{ex}}",            "role": "calculated",   "kind": "matrix", "shape": "Az x Rg",           "desc": "extraction fit quality: refit mixture against the curve it was fit to",                                   "sample": [["0.99", "0.97"], ["0.98", "0.99"]]},
            {"id": "xfloor",   "tex": r"\epsilon_{\mathrm{floor}}",   "role": "final",        "kind": "scalar", "shape": "1",                 "desc": "measurement floor: same extractor on GT curves scored against the exact GT parameters",                  "sample": "0.12"},
            {"id": "kz",       "tex": r"k_z",                        "role": "measured",     "kind": "tensor", "shape": "T x Az x Rg",       "desc": "per-pixel interferometric wavenumber field (rad/m), T=1+N_s",                                            "sample": [["0.05", "0.06"], ["0.04", "0.05"]]},
            {"id": "meas",     "tex": r"\tilde{\gamma}",             "role": "intermediate", "kind": "tensor", "shape": "N_s x Az x Rg",     "desc": "multilooked measured interferogram unit phasors",                                                        "sample": [["1+0j", "0.7+0.7j"], ["0+1j", "0.9-0.1j"]]},
            {"id": "coh",      "tex": r"E_{\gamma}",                 "role": "final",        "kind": "matrix", "shape": "Az x Rg",           "desc": "per-pixel coherence-resynthesis error map (pred vs GT)",                                                 "sample": [["0.02", "0.05"], ["0.01", "0.03"]]},
            {"id": "pha",      "tex": r"\rho_{\varphi}",             "role": "calculated",   "kind": "scalar", "shape": "1",                 "desc": "mean measured-vs-synthesised phase agreement",                                                           "sample": "0.78"},
        ]
        steps = [
            {
                "id": "load", "title": "Strict run reconstruction", "phase": "Load run",
                "note": "The trained architecture is rebuilt verbatim from run_summary.json and the saved model config, the best-epoch weights (params), x-axis and per-slot norm stats are restored, and the predictor is wrapped with the norm-stats amplitude ceiling (amp_max); inference requires a single contiguous split region or stitching aborts loudly.",
                "inputs": ["ckpt"], "outputs": ["xaxis"],
                "lines": [
                    [{"id": "ckpt", "tex": r"\theta^{\star}", "role": "measured"}, {"tex": "="}, {"tex": r"\mathrm{ckpt[params]}\ @\ \mathrm{best\ epoch},\qquad"}, {"id": "xaxis", "tex": r"\mathbf{x}", "role": "measured"}, {"tex": r"= \{x_n\}_{n=1}^{N}"}],
                    [{"tex": r"|\Omega_{\mathrm{split}}| = 1\quad(\text{one contiguous crop, else abort})"}],
                ],
            },
            {
                "id": "predict", "title": "Windowed prediction", "phase": "Windowed predict",
                "note": "Under no-grad the wrapped model maps every normalised patch on the deterministic sliding-window grid to raw normalised parameters; patches are consumed in grid order so the stitched cube has no holes.",
                "inputs": ["xhat"], "outputs": ["znorm"],
                "lines": [
                    [{"id": "znorm", "tex": r"\hat{\mathbf{z}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"f_{\theta^{\star}}\!\big("}, {"id": "xhat", "tex": r"\hat{\mathbf{x}}", "role": "measured"}, {"tex": r"\big)"}],
                ],
            },
            {
                "id": "idenorm", "title": "Denormalise and hard clamp", "phase": "Windowed predict",
                "note": "Inside the model wrapper the raw output is denormalised by the per-slot output stats then hard-clamped with leaky_slope=0 to physical bounds: amplitude to [0, a_max], mean to the elevation axis, spread to half a bin up to half the span.",
                "inputs": ["znorm"], "outputs": ["th"],
                "lines": [
                    [{"id": "th", "tex": r"\hat{a}_k", "role": "calculated"}, {"tex": r"= \mathrm{clip}(\tilde a_k,\,0,\,a_{\max}),\quad \hat{\mu}_k = \mathrm{clip}(\tilde\mu_k,\,x_{\min},\,x_{\max})"}],
                    [{"id": "th", "tex": r"\hat{\sigma}_k", "role": "calculated"}, {"tex": r"= \mathrm{clip}\!\big(\tilde\sigma_k,\ \tfrac12 x_{\mathrm{step}},\ \tfrac12 x_{\mathrm{range}}\big),\quad x_{\mathrm{step}} = \tfrac{x_{\max}-x_{\min}}{N-1}"}],
                ],
            },
            {
                "id": "align", "title": "GT denormalise and mu-sort", "phase": "Windowed predict",
                "note": "GT params are denormalised by the dataset output stats (no clamp), then per pixel the slots are argsorted by mean with inactive slots (amplitude at or below 1e-3) pushed to the tail, giving GT a canonical mu-ordered storage order for downstream matching.",
                "inputs": ["thgt"], "outputs": ["thgts"],
                "lines": [
                    [{"id": "thgts", "tex": r"\theta^{\mathrm{GT}}_{\pi}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{take}\big("}, {"id": "thgt", "tex": r"\theta^{\mathrm{GT}}", "role": "measured"}, {"tex": r",\ \pi^{\star}\big),\quad \pi^{\star} = \operatorname{argsort}_k\,\kappa_k"}],
                    [{"tex": r"\kappa_k = \mu^{\mathrm{GT}}_k\ \ \text{if}\ a^{\mathrm{GT}}_k > 10^{-3},\ \ \text{else}\ +\infty"}],
                ],
            },
            {
                "id": "recon", "title": "Curve reconstruction", "phase": "Windowed predict",
                "note": "Each patch's parameters, the clamped prediction and the mu-sorted GT alike, are evaluated on the elevation axis into a spectrum; amplitudes are rectified at zero and the kernel denominator is 2 sigma^2 + 1e-8 with no sigma floor.",
                "inputs": ["th", "xaxis"], "outputs": ["p"],
                "lines": [
                    [{"id": "p", "tex": r"\mathbf{p}_n", "role": "intermediate"}, {"tex": "="}, {"tex": r"\sum_{k} \max("}, {"id": "th", "tex": r"\hat{a}_k", "role": "calculated"}, {"tex": r",0)\,\exp\!\Big(-\tfrac{(x_n-\hat{\mu}_k)^2}{2\hat{\sigma}_k^2 + 10^{-8}}\Big)"}],
                ],
            },
            {
                "id": "window", "title": "Separable Hann window", "phase": "Cube stitch",
                "note": "A separable Hann window de-emphasises patch borders; each axis factor is floored at 1e-3 before the outer product, so every covered position keeps a strictly positive overlap weight.",
                "inputs": [], "outputs": ["win"],
                "lines": [
                    [{"id": "winv", "tex": r"w_v[i]", "role": "intermediate"}, {"tex": "="}, {"tex": r"\max\!\Big(0.5 - 0.5\cos\tfrac{2\pi(i+0.5)}{P},\ 10^{-3}\Big)"}],
                    [{"id": "win", "tex": r"w", "role": "intermediate"}, {"tex": "="}, {"id": "winv", "tex": r"w_v", "role": "intermediate"}, {"tex": r"\otimes\ w_h"}],
                ],
            },
            {
                "id": "ola", "title": "Weighted overlap-add", "phase": "Cube stitch",
                "note": "The pred and GT curve patches are stitched by weighted overlap-add: each windowed patch is scattered additively into the value accumulator at its grid origin while the window itself accumulates in a parallel weight buffer, so the blend is order-independent.",
                "inputs": ["p", "win"], "outputs": ["acc", "wacc"],
                "lines": [
                    [{"id": "acc", "tex": r"A", "role": "intermediate"}, {"tex": r"\mathrel{+}=\ "}, {"id": "p", "tex": r"\mathbf{p}", "role": "intermediate"}, {"tex": r"\cdot"}, {"id": "win", "tex": r"w", "role": "intermediate"}, {"tex": r",\qquad"}, {"id": "wacc", "tex": r"W", "role": "intermediate"}, {"tex": r"\mathrel{+}=\ w"}],
                ],
            },
            {
                "id": "finalise", "title": "Curve cube finalisation", "phase": "Cube stitch",
                "note": "The pred and GT curve cubes are formed by dividing the value accumulator by the weight accumulator and trimming the grid padding to the scene; a coverage guard raises if any scene pixel received zero weight.",
                "inputs": ["acc", "wacc"], "outputs": ["cube"],
                "lines": [
                    [{"id": "cube", "tex": r"\hat{C}", "role": "final"}, {"tex": "="}, {"tex": r"\dfrac{"}, {"id": "acc", "tex": r"A", "role": "intermediate"}, {"tex": r"}{"}, {"id": "wacc", "tex": r"W", "role": "intermediate"}, {"tex": r"}\ \Big|_{\mathrm{trim}},\qquad W > 0\ \ \forall\,(a,r)"}],
                ],
            },
            {
                "id": "paramstitch", "title": "Parameter select-stitch", "phase": "Cube stitch",
                "note": "Parameter cubes are not blended: at each pixel the patch with the largest Hann centrality wins, overwriting the running value wherever its centrality exceeds the incumbent; inactive GT slots then have their mu and sigma set to NaN before scoring.",
                "inputs": ["th", "win"], "outputs": ["params"],
                "lines": [
                    [{"id": "params", "tex": r"\hat{\Theta}", "role": "final"}, {"tex": r"[:,m] = "}, {"id": "th", "tex": r"\hat{\theta}", "role": "calculated"}, {"tex": r"[:,m],\quad m = \big\{"}, {"id": "win", "tex": r"w", "role": "intermediate"}, {"tex": r" > w^{\star}\big\},\ \ w^{\star}\!\leftarrow\! w[m]"}],
                    [{"id": "paramsgt", "tex": r"\Theta^{\mathrm{GT}}", "role": "measured"}, {"tex": r"[\mu_k,\sigma_k] = \mathrm{NaN}\ \ \text{where}\ a^{\mathrm{GT}}_k \le 10^{-3}"}],
                ],
            },
            {
                "id": "curveparams", "title": "Curve parameter extraction", "phase": "Curve param extraction",
                "note": "Only for runs whose model predicts elevation curves rather than Gaussian parameters (JEPA coupled to a profile autoencoder), and only while extract_curve_params is on. K Gaussians are refit to every stitched predicted curve so the entire parameter analysis below becomes reachable: peaks are ranked by prominence, each width comes from the half-maximum crossing around its peak, and the amplitudes solve a ridge-regularised non-negative least squares against the curve with those centres and widths held fixed. Components are then sorted by position, which is why slot-organisation statistics are suppressed for extracted parameters: the slot index is imposed by the sort, not learned. The identical extractor is run on the GT curves and scored against the exact GT parameters, and that error is the measurement floor every extracted parameter error must be read against.",
                "inputs": ["cube"], "outputs": ["xpk", "xsig", "xamp", "xr2", "xfloor"],
                "lines": [
                    [{"id": "xpk", "tex": r"\hat{\mu}^{\mathrm{ex}}_k", "role": "intermediate"}, {"tex": r"= x_{n_k},\qquad n_k \in \operatorname{top-}K\ \text{prominence peaks of}\ "}, {"id": "cube", "tex": r"\hat{C}_{:,a,r}", "role": "final"}],
                    [{"id": "xsig", "tex": r"\hat{\sigma}^{\mathrm{ex}}_k", "role": "intermediate"}, {"tex": r"= \dfrac{\mathrm{FWHM}_k}{2\sqrt{2\ln 2}},\qquad \mathrm{FWHM}_k = \Delta x\,\big|\{n : \hat{C}_n \ge \tfrac12 \hat{C}_{n_k}\ \text{contiguous with}\ n_k\}\big|"}],
                    [{"id": "xamp", "tex": r"\hat{\mathbf{a}}^{\mathrm{ex}}", "role": "calculated"}, {"tex": r"= \max\!\big((G^{\top}G + \lambda I)^{-1} G^{\top}"}, {"id": "cube", "tex": r"\hat{C}", "role": "final"}, {"tex": r",\ 0\big),\qquad G_{nk} = \exp\!\Big(-\tfrac{(x_n - \hat{\mu}^{\mathrm{ex}}_k)^2}{2(\hat{\sigma}^{\mathrm{ex}}_k)^2}\Big)"}],
                    [{"id": "xfloor", "tex": r"\epsilon_{\mathrm{floor}}", "role": "final"}, {"tex": r"= \mathrm{MAE}_{\mu}\big(\mathcal{E}(C^{\mathrm{GT}}),\ \Theta^{\mathrm{GT}}\big),\qquad \mathcal{E} = \text{the same extractor}"}],
                ],
            },
            {
                "id": "pixelmaps", "title": "Per-pixel metric maps", "phase": "Pixel metrics",
                "note": "Five per-pixel maps are reduced over the N elevation bins of the stitched curve cubes: MSE, MAE, R-squared (denominator floored at 1e-12), cosine similarity (norms floored at 1e-8), and absolute peak-bin index error.",
                "inputs": ["cube", "cubegt"], "outputs": ["pr2"],
                "lines": [
                    [{"id": "pr2", "tex": r"R^2_{a,r}", "role": "calculated"}, {"tex": "="}, {"tex": r"1 - \dfrac{\sum_n(\hat C_{n,a,r}-C_{n,a,r})^2}{\sum_n(C_{n,a,r}-\bar C_{a,r})^2 + 10^{-12}}"}],
                    [{"tex": r"\Delta n_{a,r} = \big|\arg\max_n \hat C_{n,a,r} - \arg\max_n C_{n,a,r}\big|"}],
                ],
            },
            {
                "id": "globalcurve", "title": "Global curve metrics", "phase": "Curve metrics",
                "note": "Cube-wide scalars at physical (denorm) scale: MSE, RMSE, overall R-squared (eps 1e-12), and PSNR whose peak signal is the GT-only dynamic range C_max minus C_min.",
                "inputs": ["cube", "cubegt"], "outputs": ["r2", "psnr"],
                "lines": [
                    [{"id": "r2", "tex": r"R^2", "role": "final"}, {"tex": "="}, {"tex": r"1 - \dfrac{\sum_{n,a,r}(\hat C - C)^2}{\sum_{n,a,r}(C - \bar C)^2 + 10^{-12}}"}],
                    [{"id": "psnr", "tex": r"\mathrm{PSNR}", "role": "calculated"}, {"tex": "="}, {"tex": r"10\log_{10}\dfrac{(C_{\max}-C_{\min})^2}{\mathrm{MSE}_{\mathrm{curve}}}\ \ \text{(dB)}"}],
                ],
            },
            {
                "id": "elevssim", "title": "Per-elevation metrics and SSIM", "phase": "Curve metrics",
                "note": "Per elevation bin (all pixels as samples): MAE, RMSE, R-squared and a cross-entropy between column-normalised distributions; plus mean SSIM over all slices along each axis, on both denorm and unit-area cubes at each slice's GT data range.",
                "inputs": ["cube", "cubegt"], "outputs": ["elevr2"],
                "lines": [
                    [{"id": "elevr2", "tex": r"R^2_{\mathrm{elev}}(n)", "role": "calculated"}, {"tex": "="}, {"tex": r"1 - \dfrac{\sum_{a,r}(\hat C_{n,a,r}-C_{n,a,r})^2}{\sum_{a,r}(C_{n,a,r}-\bar C_n)^2 + 10^{-12}}"}],
                    [{"tex": r"\mathrm{CE}(n) = -\tfrac{1}{A_z R_g}\textstyle\sum_{a,r} \bar p^{\mathrm{GT}}_{n}\log \bar p^{\mathrm{pred}}_{n},\quad \bar p_n = \tfrac{C_n}{\sum_m C_m}"}],
                ],
            },
            {
                "id": "paramslot", "title": "Matched Gaussian metrics", "phase": "Param metrics",
                "note": "On active pixels each predicted pixel's Gaussians are matched to its GT Gaussians by exact brute-force optimal assignment over all K! permutations on |dmu| (inactive pairs cost 1e7, no Hungarian fallback): matched mu and sigma MAE/RMSE over matched pairs, plus detection recall, precision and F1 counting a hit when |dmu| is at most 5 elevation units.",
                "inputs": ["params", "paramsgt"], "outputs": ["gmu", "mf1"],
                "lines": [
                    [{"id": "gmu", "tex": r"\mathrm{MAE}_{\mu}", "role": "calculated"}, {"tex": "="}, {"tex": r"\tfrac{1}{|\mathcal M|}\textstyle\sum_{(i,j)\in\mathcal M}|\hat\mu_{i}-\mu^{\mathrm{GT}}_{j}|,\quad \pi^{\star}=\operatorname*{argmin}_{\pi}\textstyle\sum_i|\hat\mu_i-\mu^{\mathrm{GT}}_{\pi(i)}|"}],
                    [{"id": "mf1", "tex": r"F_1", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{2\,\mathrm{Prec}\,\mathrm{Rec}}{\mathrm{Prec}+\mathrm{Rec}},\quad \text{hit}:\ |\Delta\mu|\le 5"}],
                ],
            },
            {
                "id": "reduced", "title": "Reduced Capon re-synthesis", "phase": "Reduced baseline",
                "note": "Enabled by default and run only when the run trained on a strict secondary subset: a classical Capon tomogram is re-synthesised from the primary plus that subset (effort high, stetools env); after an advisory orientation check the GT, prediction and reduced cubes are unit-area normalised (eps 1e-12) and the per-pixel MSE improvement of the network over the reduced baseline is mapped.",
                "inputs": ["redc", "cube", "cubegt"], "outputs": ["dimp"],
                "lines": [
                    [{"tex": r"\bar y_{n,a,r} = \dfrac{y_{n,a,r}}{\max(\sum_n y_{n,a,r},\,10^{-12})}\quad (y\in\{C,\hat C,\mathbf{r}\})"}],
                    [{"id": "dimp", "tex": r"\Delta_{a,r}", "role": "final"}, {"tex": "="}, {"tex": r"\mathrm{MSE}^{\mathrm{red}}_{a,r} - \mathrm{MSE}^{\mathrm{pred}}_{a,r}"}],
                ],
            },
            {
                "id": "consistency", "title": "Interferometric data consistency", "phase": "Data consistency",
                "note": "Enabled by default: predicted and GT profiles are reprojected to per-track unit coherences through the per-pixel kz field over pixels whose GT power exceeds physics_floor=1e-3, giving per-pixel coherence-resynthesis and covariance-matching error maps; the phase_multilook=9 multilooked measured interferograms are then correlated against the synthesised coherence, with a conjugate-steering flipped variant as a kz sign check.",
                "inputs": ["cube", "cubegt", "kz", "meas"], "outputs": ["coh", "pha"],
                "lines": [
                    [{"id": "coh", "tex": r"E_{\gamma}", "role": "final"}, {"tex": "="}, {"tex": r"\tfrac{1}{T}\textstyle\sum_{i=0}^{T-1}\Big|\tfrac{\hat\gamma_i}{\hat p_0} - \tfrac{\gamma_i}{p_0}\Big|^2,\ \ \gamma_i = \textstyle\sum_n e^{\,j k_{z,i,n} x_n} C_n\,dx"}],
                    [{"id": "pha", "tex": r"\rho_{\varphi}", "role": "calculated"}, {"tex": "="}, {"tex": r"\Big|\tfrac{1}{|V|}\textstyle\sum_{V} \tilde\gamma\,\overline{(\hat\gamma_i/|\hat\gamma_i|)}\Big|,\quad p_0 = \max(\textstyle\sum_n C_n\,dx,\ 10^{-3})"}],
                ],
            },
        ]
        return {
            "key": "inference", "name": "Inference (Stitching)",
            "blurb": "The trained run is rebuilt strictly from its saved config, then every sliding-window patch is predicted, denormalised and hard-clamped, reconstructed to an elevation spectrum, blended into dense pred and GT cubes by weighted overlap-add for curves and highest-centrality selection for parameters. Runs that predict curves directly have K Gaussians refit to each stitched curve, against a measurement floor obtained by running the same extractor on the GT curves, so they reach the same parameter analysis. Everything is then scored by the full per-pixel, curve, per-elevation, matched-parameter, reduced-Capon-baseline and interferometric-consistency suite.",
            "nodes": nodes, "steps": steps,
        }

    def _profile_ae_infer(self) -> dict:
        """Returns the flow for replaying a trained profile autoencoder on a held-out split."""
        nodes = [
            {"id": "gparams", "tex": r"\theta^{\mathrm{GT}}",                 "role": "measured",     "kind": "tensor", "shape": "3K x Az x Rg",  "desc": "stored per-pixel Gaussian parameters (a, mu, sigma per slot)",            "sample": ["a_1", "mu_1", "sig_1", "..."]},
            {"id": "xaxis",   "tex": r"\mathbf{x}",                           "role": "measured",     "kind": "vector", "shape": "L",             "desc": "elevation axis (m), linspace(x_min, x_max, L)",                           "sample": ["-20", "-19.6", "...", "80"]},
            {"id": "ckpt",    "tex": r"\theta^{\star}",                       "role": "measured",     "kind": "vector", "shape": "|theta|",       "desc": "best-epoch AE weights (encoder + decoder); elevation x-axis bundled",     "sample": ["0.31", "-0.08", "..."]},
            {"id": "norm",    "tex": r"(\ell,\,s)",                           "role": "measured",     "kind": "vector", "shape": "2",             "desc": "log1p location and scale fitted on the train split (scale floored 1e-6)", "sample": ["0.12", "0.94"]},
            {"id": "sel",     "tex": r"\mathcal{S}",                          "role": "intermediate", "kind": "set",    "shape": "N",             "desc": "kept pixel indices: all active plus a fraction of empties, shuffled",     "sample": ["37", "5", "210", "..."]},
            {"id": "curve",   "tex": r"c",                                    "role": "intermediate", "kind": "tensor", "shape": "B x L",         "desc": "mixture-built GT elevation profile, the AE input and reference",          "sample": [["0.00", "0.62"], ["0.31", "0.88"]]},
            {"id": "cn",      "tex": r"c_{\mathrm{n}}",                       "role": "intermediate", "kind": "tensor", "shape": "B x L",         "desc": "log1p-standardised profile fed to the network",                           "sample": [["-0.13", "0.51"], ["0.09", "0.74"]]},
            {"id": "X",       "tex": r"\mathbf{X}",                           "role": "intermediate", "kind": "tensor", "shape": "B x L x 1 x 1", "desc": "profile cast to an L-channel 1x1 spatial map",                            "sample": [["-0.13"], ["0.51"]]},
            {"id": "z",       "tex": r"\mathbf{z}",                           "role": "intermediate", "kind": "tensor", "shape": "B x d",         "desc": "per-profile latent embedding after embedding-norm (d = 24 default)",      "sample": ["0.22", "-1.1", "0.70", "..."]},
            {"id": "chatn",   "tex": r"\hat{c}_{\mathrm{n}}",                 "role": "intermediate", "kind": "tensor", "shape": "B x L",         "desc": "decoded reconstruction in normalised space",                              "sample": [["-0.12", "0.50"], ["0.10", "0.72"]]},
            {"id": "pred",    "tex": r"\hat{c}",                              "role": "calculated",   "kind": "tensor", "shape": "B x L",         "desc": "denormalised reconstruction, physical units",                             "sample": [["0.01", "0.60"], ["0.30", "0.86"]]},
            {"id": "gt",      "tex": r"c^{\mathrm{gt}}",                      "role": "calculated",   "kind": "tensor", "shape": "B x L",         "desc": "inverse-normalised reference profile (metric target)",                    "sample": [["0.00", "0.62"], ["0.31", "0.88"]]},
            {"id": "emb",     "tex": r"\mathbf{Z}",                           "role": "final",        "kind": "matrix", "shape": "N x d",         "desc": "persisted embedding matrix, saved to embeddings.npy",                     "sample": [["0.22", "-1.1"], ["0.05", "0.70"]]},
            {"id": "rec",     "tex": r"R^2",                                  "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "physical reconstruction scores: R2, MSE, RMSE, MAE",                      "sample": "0.94"},
            {"id": "shp",     "tex": r"\rho",                                 "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "shape fidelity: mean Pearson and relative L2 over active curves",         "sample": "0.98"},
            {"id": "pwr",     "tex": r"\delta_P",                             "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "integrated-power relative error and peak-location MAE (active curves)",   "sample": "0.04"},
            {"id": "estat",   "tex": r"\langle\lVert\mathbf{z}\rVert\rangle", "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "embedding norm, per-dim spread and active-dim fraction",                  "sample": "1.00"},
            {"id": "metrics", "tex": r"\mathcal{M}",                          "role": "final",        "kind": "set",    "shape": "-",             "desc": "metrics.json bundle (physical, normalised, shape, power, embedding)",     "sample": ["mse", "r2", "pearson", "..."]},
            {"id": "report",  "tex": r"\mathcal{R}",                          "role": "final",        "kind": "set",    "shape": "-",             "desc": "report.md and rendered figure sets",                                      "sample": ["report.md", "figures/"]},
        ]
        steps = [
            {
                "id": "paei_restore", "title": "Strict run reconstruction", "phase": "A - Load run",
                "note": "The run is rebuilt verbatim from run_summary.json and the saved autoencoder config; it aborts unless model_name is 'profile_ae' (backbone and JEPA runs must use 'infer'). The embedding width is out_channels, and the profile length L must agree across the dataset, the run summary and the checkpoint x-axis or loading fails loudly.",
                "inputs": ["ckpt"], "outputs": ["xaxis"],
                "lines": [
                    [{"tex": r"\texttt{model\_name} = \texttt{profile\_ae},\quad d = C_{\mathrm{out}},\quad"}, {"id": "xaxis", "tex": r"\mathbf{x}", "role": "measured"}, {"tex": r"= \{x_n\}_{n=1}^{L}"}],
                    [{"tex": r"L = |"}, {"id": "xaxis", "tex": r"\mathbf{x}", "role": "measured"}, {"tex": r"| = \texttt{x\_axis\_length} = |"}, {"id": "ckpt", "tex": r"\theta^{\star}", "role": "measured"}, {"tex": r".x_{\mathrm{axis}}|\quad(\text{else abort})"}],
                ],
            },
            {
                "id": "paei_select", "title": "Active-pixel selection", "phase": "A - Load run",
                "note": "Only pixels whose largest slot amplitude clears the zero threshold are fitted; every active pixel is kept and a small fraction of empty pixels (keep_empty_frac) is sampled in, then the index is shuffled. Default inference keeps all active pixels (pixel_subsample = 1).",
                "inputs": ["gparams"], "outputs": ["sel"],
                "lines": [
                    [{"id": "sel", "tex": r"\mathcal{S}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\big\{\,i : \max_k\,a_{i,k}\big("}, {"id": "gparams", "tex": r"\theta^{\mathrm{GT}}", "role": "measured"}, {"tex": r"\big) > \tau_a\big\}\ \cup\ \mathrm{Sample}(\mathcal{E},\,f_e),\quad \tau_a = 10^{-3},\ f_e = 0.05"}],
                ],
            },
            {
                "id": "paei_curves", "title": "Profile reconstruction from parameters", "phase": "A - Load run",
                "note": "Each kept pixel's supervised profile is rebuilt from its Gaussian parameters as an additive mixture on the elevation axis; sigma is floored at 1e-6 and the exponent clipped to [-100, 0] before the sum. This mixture curve is exactly the AE input and the reconstruction reference.",
                "inputs": ["gparams", "xaxis"], "outputs": ["curve"],
                "lines": [
                    [{"id": "curve", "tex": r"c(x_n)", "role": "intermediate"}, {"tex": "="}, {"tex": r"\sum_{k}"}, {"id": "gparams", "tex": r"a_k", "role": "measured"}, {"tex": r"\exp\!\Big(\mathrm{clip}\big(-\tfrac{(x_n-"}, {"id": "gparams", "tex": r"\mu_k", "role": "measured"}, {"tex": r")^2}{2\max("}, {"id": "gparams", "tex": r"\sigma_k", "role": "measured"}, {"tex": r",\,\sigma_{\mathrm{flr}})^2},\,-100,\,0\big)\Big),\ \ \sigma_{\mathrm{flr}}=10^{-6}"}],
                ],
            },
            {
                "id": "paei_normalise", "title": "Log1p standardisation", "phase": "A - Load run",
                "note": "The dataset normaliser log1p-compresses the non-negative profile then standardises it by the train-split location and scale; the scale is floored at 1e-6. This is the dimensionless space the encoder consumes.",
                "inputs": ["curve", "norm"], "outputs": ["cn"],
                "lines": [
                    [{"id": "cn", "tex": r"c_{\mathrm{n}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\dfrac{\log\!\big(1+\max("}, {"id": "curve", "tex": r"c", "role": "intermediate"}, {"tex": r",0)\big) - "}, {"id": "norm", "tex": r"\ell", "role": "measured"}, {"tex": r"}{"}, {"id": "norm", "tex": r"s", "role": "measured"}, {"tex": r"},\qquad s = \max(\mathrm{scale},\,10^{-6})"}],
                ],
            },
            {
                "id": "paei_reshape", "title": "Cast profile to channel map", "phase": "B - Reconstruct",
                "note": "Before the encoder each profile is cast to an L-channel tensor over a single 1x1 spatial cell, so the profile-length axis becomes the channel axis that the 1x1-convolution MLP mixes per pixel.",
                "inputs": ["cn"], "outputs": ["X"],
                "lines": [
                    [{"id": "X", "tex": r"\mathbf{X}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{reshape}\big("}, {"id": "cn", "tex": r"c_{\mathrm{n}}", "role": "intermediate"}, {"tex": r"\big):\ (B, L)\ \mapsto\ (B, L, 1, 1)"}],
                ],
            },
            {
                "id": "paei_encode", "title": "Encode to latent embedding", "phase": "B - Reconstruct",
                "note": "The encoder MLP (1x1 convolutions) contracts the L profile channels to a d-dimensional latent, which is then passed through the configured embedding normalisation. The default is a per-sample layernorm over the d channels (eps 1e-5, learnable affine); l2 divides by the norm floored at 1e-6, and none is the identity.",
                "inputs": ["X", "ckpt"], "outputs": ["z"],
                "lines": [
                    [{"id": "z", "tex": r"\mathbf{z}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathcal{N}\!\big(f_{\mathrm{enc}}("}, {"id": "X", "tex": r"\mathbf{X}", "role": "intermediate"}, {"tex": r")\big),\qquad f_{\mathrm{enc}}:\ \mathbb{R}^{L}\!\to\mathbb{R}^{d},\ \ d = 24"}],
                    [{"tex": r"\mathcal{N}_{\mathrm{LN}}(\mathbf{z}) = \gamma\odot\dfrac{\mathbf{z}-\mu_z}{\sqrt{\sigma_z^2 + 10^{-5}}} + \beta,\qquad \mathcal{N}_{\ell_2}(\mathbf{z}) = \dfrac{\mathbf{z}}{\max(\lVert\mathbf{z}\rVert_2,\,10^{-6})}"}],
                ],
            },
            {
                "id": "paei_decode", "title": "Decode reconstruction", "phase": "B - Reconstruct",
                "note": "The decoder MLP expands the latent back to L channels, reconstructing the profile in the same normalised space; the whole model runs under no_grad in eval mode.",
                "inputs": ["z"], "outputs": ["chatn"],
                "lines": [
                    [{"id": "chatn", "tex": r"\hat{c}_{\mathrm{n}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"f_{\mathrm{dec}}\!\big("}, {"id": "z", "tex": r"\mathbf{z}", "role": "intermediate"}, {"tex": r"\big),\qquad f_{\mathrm{dec}}:\ \mathbb{R}^{d}\!\to\mathbb{R}^{L}"}],
                ],
            },
            {
                "id": "paei_denorm", "title": "Inverse normalisation", "phase": "B - Reconstruct",
                "note": "Both the reconstruction and the input are inverse-normalised to physical units: multiply by the scale, add the location, then clip the log-domain value to [0, log1p(1000)] before expm1, bounding the recovered profile to [0, 1000]. The inverse-normalised input is the metric reference.",
                "inputs": ["chatn", "cn", "norm"], "outputs": ["gt", "pred"],
                "lines": [
                    [{"id": "pred", "tex": r"\hat{c}", "role": "calculated"}, {"tex": "="}, {"tex": r"\operatorname{expm1}\!\Big(\operatorname{clip}\big("}, {"id": "chatn", "tex": r"\hat{c}_{\mathrm{n}}", "role": "intermediate"}, {"tex": r"\,s + "}, {"id": "norm", "tex": r"\ell", "role": "measured"}, {"tex": r",\ 0,\ \log(1{+}C)\big)\Big),\quad C = 1000"}],
                    [{"id": "gt", "tex": r"c^{\mathrm{gt}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\operatorname{expm1}\!\Big(\operatorname{clip}\big("}, {"id": "cn", "tex": r"c_{\mathrm{n}}", "role": "intermediate"}, {"tex": r"\,s + "}, {"id": "norm", "tex": r"\ell", "role": "measured"}, {"tex": r",\ 0,\ \log(1{+}C)\big)\Big)"}],
                ],
            },
            {
                "id": "paei_embed", "title": "Persist embeddings", "phase": "C - Embeddings",
                "note": "The per-profile latents are concatenated across all batches and saved to embeddings.npy as the split's embedding matrix, the primary artifact for downstream latent-space analysis.",
                "inputs": ["z"], "outputs": ["emb"],
                "lines": [
                    [{"id": "emb", "tex": r"\mathbf{Z}", "role": "final"}, {"tex": "="}, {"tex": r"\big[\,"}, {"id": "z", "tex": r"\mathbf{z}_1;\ \dots;\ \mathbf{z}_N", "role": "intermediate"}, {"tex": r"\,\big]\ \in\ \mathbb{R}^{N\times d}\ \longrightarrow\ \texttt{embeddings.npy}"}],
                ],
            },
            {
                "id": "paei_physical", "title": "Physical reconstruction error", "phase": "D - Metrics",
                "note": "Physical-scale reconstruction errors over all kept curves and bins: mean-squared and mean-absolute error, RMSE, and the coefficient of determination against the global GT mean with a 1e-8 stabiliser on the total sum of squares.",
                "inputs": ["pred", "gt"], "outputs": ["rec"],
                "lines": [
                    [{"id": "rec", "tex": r"R^2", "role": "calculated"}, {"tex": "="}, {"tex": r"1 - \dfrac{\sum_{i,n}\big("}, {"id": "pred", "tex": r"\hat{c}", "role": "calculated"}, {"tex": r"-"}, {"id": "gt", "tex": r"c^{\mathrm{gt}}", "role": "calculated"}, {"tex": r"\big)^2}{\sum_{i,n}\big(c^{\mathrm{gt}} - \bar{c}^{\mathrm{gt}}\big)^2 + \varepsilon},\quad \varepsilon = 10^{-8}"}],
                    [{"tex": r"\mathrm{MSE} = \big\langle(\hat{c}-c^{\mathrm{gt}})^2\big\rangle,\quad \mathrm{RMSE} = \sqrt{\mathrm{MSE}},\quad \mathrm{MAE} = \big\langle|\hat{c}-c^{\mathrm{gt}}|\big\rangle"}],
                ],
            },
            {
                "id": "paei_shape", "title": "Profile-shape fidelity", "phase": "D - Metrics",
                "note": "On active curves only (GT peak above 1e-3): the magnitude-free shape agreement is the Pearson correlation of the mean-centred profiles and the relative L2 error, each averaged over active curves with a 1e-8 denominator floor.",
                "inputs": ["pred", "gt"], "outputs": ["shp"],
                "lines": [
                    [{"id": "shp", "tex": r"\rho", "role": "calculated"}, {"tex": "="}, {"tex": r"\Big\langle\dfrac{\langle\tilde{c}^{\mathrm{gt}},\,\tilde{\hat{c}}\rangle}{\lVert\tilde{c}^{\mathrm{gt}}\rVert\,\lVert\tilde{\hat{c}}\rVert + \varepsilon}\Big\rangle_{a},\qquad \tilde{c} = c - \bar{c}"}],
                    [{"tex": r"\mathrm{relL2} = \Big\langle\dfrac{\lVert\hat{c}-c^{\mathrm{gt}}\rVert_2}{\lVert c^{\mathrm{gt}}\rVert_2 + \varepsilon}\Big\rangle_{a}"}],
                ],
            },
            {
                "id": "paei_power", "title": "Power and peak-location error", "phase": "D - Metrics",
                "note": "Also over active curves: the integrated profile power is the trapezoidal area under the curve, giving a relative power error, and the peak-location MAE is the distance between the argmax elevations of the reconstruction and the GT; the peak-amplitude relative error is reported alongside.",
                "inputs": ["pred", "gt", "xaxis"], "outputs": ["pwr"],
                "lines": [
                    [{"id": "pwr", "tex": r"\delta_P", "role": "calculated"}, {"tex": "="}, {"tex": r"\Big\langle\dfrac{|P(\hat{c}) - P(c^{\mathrm{gt}})|}{|P(c^{\mathrm{gt}})| + \varepsilon}\Big\rangle_{a},\qquad P(c) = \mathrm{trapz}\big(c,\,"}, {"id": "xaxis", "tex": r"\mathbf{x}", "role": "measured"}, {"tex": r"\big)"}],
                    [{"tex": r"\mathrm{MAE}_{\mathrm{peak}} = \Big\langle\big|"}, {"id": "xaxis", "tex": r"\mathbf{x}", "role": "measured"}, {"tex": r"[\arg\max\hat{c}] - "}, {"id": "xaxis", "tex": r"\mathbf{x}", "role": "measured"}, {"tex": r"[\arg\max c^{\mathrm{gt}}]\big|\Big\rangle_{a}"}],
                ],
            },
            {
                "id": "paei_embstat", "title": "Embedding statistics", "phase": "D - Metrics",
                "note": "Latent-health diagnostics over the embedding matrix: the mean L2 norm of the embeddings, the mean per-dimension standard deviation across curves, and the fraction of latent dimensions whose spread exceeds 1e-4, a collapse guard.",
                "inputs": ["emb"], "outputs": ["estat"],
                "lines": [
                    [{"id": "estat", "tex": r"\langle\lVert\mathbf{z}\rVert\rangle", "role": "calculated"}, {"tex": "="}, {"tex": r"\tfrac{1}{N}\textstyle\sum_i \big\lVert"}, {"id": "emb", "tex": r"\mathbf{Z}_i", "role": "final"}, {"tex": r"\big\rVert_2,\qquad f_{\mathrm{act}} = \tfrac{1}{d}\textstyle\sum_j\mathbb{1}\!\left[\operatorname{std}_i(\mathbf{Z}_{:,j}) > 10^{-4}\right]"}],
                ],
            },
            {
                "id": "paei_report", "title": "Metrics and figures", "phase": "E - Report",
                "note": "The metric bundle is written to metrics.json (physical, normalised, shape, power and embedding blocks, tagged with the split region), and, unless plots are disabled, per-curve reconstructions ranked by MSE (best, worst, random), the mean profile, an error histogram, a power scatter, an embedding-norm histogram, a latent RGB scatter and a latent RGB scene map are rendered into the markdown report. Both RGB figures rank the d latent components by their variance across the split and map the three widest to (R, G, B) after a 1-99 percentile rescale, with the channels floored at 0.15 so no sample matches the dark background. The scatter plots the two widest components against each other; the scene map sends every embedding back to its (azimuth, range) pixel through the saved pixel index, one image per split region, leaving pixels the sampler dropped in black.",
                "inputs": ["rec", "shp", "pwr", "estat"], "outputs": ["metrics", "report"],
                "lines": [
                    [{"id": "metrics", "tex": r"\mathcal{M}", "role": "final"}, {"tex": "="}, {"tex": r"\big\{"}, {"id": "rec", "tex": r"R^2", "role": "calculated"}, {"tex": ","}, {"id": "shp", "tex": r"\rho", "role": "calculated"}, {"tex": ","}, {"id": "pwr", "tex": r"\delta_P", "role": "calculated"}, {"tex": ","}, {"id": "estat", "tex": r"f_{\mathrm{act}}", "role": "calculated"}, {"tex": r",\ \dots\big\}\ \longrightarrow\ \texttt{metrics.json}"}],
                    [{"id": "report", "tex": r"\mathcal{R}", "role": "final"}, {"tex": "="}, {"tex": r"\mathrm{best/worst/random},\ \bar{c},\ \mathrm{hist}(\mathrm{MSE}),\ \mathrm{power},\ \mathrm{hist}(\lVert\mathbf{z}\rVert),\ \mathrm{RGB}\big(\mathbf{Z}_{:,j_1},\mathbf{Z}_{:,j_2},\mathbf{Z}_{:,j_3}\big)\ \longrightarrow\ \texttt{report.md}"}],
                    [{"tex": r"(j_1, j_2, j_3) = \operatorname*{arg\,top3}_{j}\ \operatorname{var}_i\big("}, {"id": "emb", "tex": r"\mathbf{Z}_{:,j}", "role": "final"}, {"tex": r"\big),\qquad \mathrm{RGB}_c = \beta + (1-\beta)\operatorname{clip}\!\Big(\tfrac{\mathbf{Z}_{:,j_c} - q_{1}}{\max(q_{99}-q_{1},\,10^{-12})},\,0,\,1\Big),\quad \beta = 0.15"}],
                    [{"tex": r"M_r\big[\lfloor s_i/W_r\rfloor,\ s_i \bmod W_r\big] = \mathrm{RGB}_i,\qquad s_i = "}, {"id": "sel", "tex": r"\mathcal{S}_i", "role": "intermediate"}, {"tex": r"- \textstyle\sum_{p<r} H_p W_p\quad(\text{black elsewhere})"}],
                ],
            },
        ]
        return {
            "key"   : "profile_ae_infer",
            "name"  : "Profile AE (Infer)",
            "blurb" : "A trained profile autoencoder is rebuilt strictly from its saved config, the held-out split's supervised profiles are re-synthesised from their Gaussian parameters and log1p-standardised, then each profile is encoded to a low-dimensional latent and decoded back; reconstructions and inputs are inverse-normalised to physical units, the latents are persisted, and the split is scored by the full physical, shape, power and embedding-health metric suite.",
            "nodes" : nodes,
            "steps" : steps,
        }

    def _image_ae_infer(self) -> dict:
        """Returns the flow for replaying a trained image autoencoder over a split."""
        nodes = [
            {"id": "wstar",  "tex": r"\theta^{\star}",     "role": "measured",     "kind": "vector", "shape": "|theta|",            "desc": "trained encoder-decoder weights from best_model.pt",     "sample": ["0.31", "-0.08", "0.12", "..."]},
            {"id": "stats",  "tex": r"(\mu_c, s_c)",       "role": "measured",     "kind": "vector", "shape": "C_in x 2",           "desc": "per-input-channel loc and scale (output stats dropped)", "sample": ["0.12", "0.94", "..."]},
            {"id": "xn",     "tex": r"\hat{\mathbf{x}}",   "role": "measured",     "kind": "tensor", "shape": "B x C_in x P x P",   "desc": "normalised input patch batch from the split loader",     "sample": [["0.41", "-0.20"], ["-0.33", "0.27"]]},
            {"id": "z",      "tex": r"\mathbf{z}",         "role": "intermediate", "kind": "tensor", "shape": "B x D x h x w",      "desc": "embedding-normalised encoder latent feature map",        "sample": [["0.22", "-0.14"], ["0.31", "0.08"]]},
            {"id": "xrecn",  "tex": r"\hat{\mathbf{x}}_n", "role": "intermediate", "kind": "tensor", "shape": "B x C_in x P x P",   "desc": "decoded reconstruction, still in normalised space",      "sample": [["0.39", "-0.18"], ["-0.30", "0.24"]]},
            {"id": "gt",     "tex": r"\mathbf{x}",         "role": "calculated",   "kind": "tensor", "shape": "N_p x C_in x P x P", "desc": "denormalised physical input (round-trip of the patch)",  "sample": [["0.90", "0.61"], ["0.55", "0.88"]]},
            {"id": "pred",   "tex": r"\tilde{\mathbf{x}}", "role": "calculated",   "kind": "tensor", "shape": "N_p x C_in x P x P", "desc": "denormalised physical reconstruction",                   "sample": [["0.88", "0.60"], ["0.57", "0.85"]]},
            {"id": "emb",    "tex": r"\bar{\mathbf{z}}",   "role": "calculated",   "kind": "vector", "shape": "D",                  "desc": "per-patch embedding, latent pooled over space",          "sample": ["0.18", "-0.05", "0.42", "..."]},
            {"id": "err",    "tex": r"e",                  "role": "intermediate", "kind": "tensor", "shape": "N_p x C_in x P x P", "desc": "physical reconstruction residual pred minus gt",         "sample": ["-0.02", "0.01", "-0.03", "..."]},
            {"id": "mse",    "tex": r"\mathrm{MSE}",       "role": "calculated",   "kind": "scalar", "shape": "1",                  "desc": "mean squared reconstruction error, physical units",      "sample": "3.1e-3"},
            {"id": "r2",     "tex": r"R^2",                "role": "calculated",   "kind": "scalar", "shape": "1",                  "desc": "coefficient of determination over all pixels",           "sample": "0.981"},
            {"id": "psnr",   "tex": r"\mathrm{PSNR}",      "role": "calculated",   "kind": "scalar", "shape": "1",                  "desc": "peak SNR (dB) from the GT dynamic range",                "sample": "34.2"},
            {"id": "nmse",   "tex": r"\mathrm{MSE}_n",     "role": "calculated",   "kind": "scalar", "shape": "1",                  "desc": "MSE after re-normalising both tensors (dimensionless)",  "sample": "4.0e-2"},
            {"id": "cmse",   "tex": r"m_c",                "role": "calculated",   "kind": "vector", "shape": "C_in",               "desc": "per-channel mean squared error",                         "sample": ["0.004", "0.002", "..."]},
            {"id": "estat",  "tex": r"\mathbf{\delta}",    "role": "calculated",   "kind": "vector", "shape": "3",                  "desc": "embedding norm, mean per-dim std, active-dim fraction",  "sample": ["5.7", "0.21", "0.83"]},
            {"id": "E",      "tex": r"E",                  "role": "final",        "kind": "matrix", "shape": "N_p x D",            "desc": "stacked patch embeddings written to embeddings.npy",     "sample": [["0.18", "-0.05"], ["0.22", "0.10"]]},
            {"id": "report", "tex": r"\mathcal{M}",        "role": "final",        "kind": "set",    "shape": "3 files",            "desc": "metrics.json plus the assembled Markdown report",        "sample": "{MSE, R2, PSNR, ...}"},
        ]
        steps = [
            {
                "id": "iaei_loadrun", "title": "Model and checkpoint load", "phase": "A - Load run",
                "note": "run_summary.json must declare model_name = image_ae or the load aborts; the architecture is rebuilt from the persisted AE config, the best_model.pt params are loaded, the embedding dimension is read as out_channels, and the model is set to eval.",
                "inputs": [], "outputs": ["wstar"],
                "lines": [
                    [{"tex": r"\texttt{model\_name} = \texttt{image\_ae}\ \Rightarrow\ f_{\theta} = (\mathrm{Enc}_{\theta},\ \mathrm{Dec}_{\theta}),\quad D = C_{\mathrm{out}}"}],
                    [{"id": "wstar", "tex": r"\theta^{\star}", "role": "measured"}, {"tex": r"\leftarrow \texttt{best\_model.pt}[\texttt{params}],\qquad f_{\theta}.\mathrm{eval}()"}],
                ],
            },
            {
                "id": "iaei_stats", "title": "Input normalization statistics", "phase": "A - Load run",
                "note": "Stats.load reads the per-slot loc and scale fitted on the train split; the output-parameter stats are dropped because the autoencoder reconstructs its own input, not the Gaussian target, so only input stats are ever applied.",
                "inputs": [], "outputs": ["stats"],
                "lines": [
                    [{"id": "stats", "tex": r"(\mu_c, s_c)", "role": "measured"}, {"tex": "="}, {"tex": r"\mathrm{Stats.load}(\texttt{meta}),\qquad \text{output stats} \to \varnothing"}],
                ],
            },
            {
                "id": "iaei_dataset", "title": "Rebuild split patches", "phase": "A - Load run",
                "note": "The persisted dataset config is replayed for the split (default test), which must resolve to a single contiguous region or the run aborts; the loader tiles it into PxP patches with shuffle off and no drop-last, and the yielded channel count must equal the trained in_channels.",
                "inputs": [], "outputs": ["xn"],
                "lines": [
                    [{"tex": r"\Omega_{\mathrm{test}}\ \text{single region},\qquad"}, {"id": "xn", "tex": r"\hat{\mathbf{x}}", "role": "measured"}, {"tex": r"\in \mathbb{R}^{B\times C_{\mathrm{in}}\times P\times P}"}],
                    [{"tex": r"C_{\mathrm{in}}^{\mathrm{data}} = C_{\mathrm{in}}^{\mathrm{train}}\quad(\text{else abort})"}],
                ],
            },
            {
                "id": "iaei_encode", "title": "Encode to latent", "phase": "B - Reconstruct",
                "note": "Under no_grad the encoder maps the normalised patch to a latent feature map, then the configured embedding norm is applied: none, L2 with eps 1e-6, or per-sample layernorm over the channel axis with var eps 1e-6.",
                "inputs": ["xn", "wstar"], "outputs": ["z"],
                "lines": [
                    [{"id": "z", "tex": r"\mathbf{z}", "role": "intermediate"}, {"tex": "="}, {"tex": r"g_{\mathrm{norm}}\!\big(\mathrm{Enc}_{\theta}("}, {"id": "xn", "tex": r"\hat{\mathbf{x}}", "role": "measured"}, {"tex": r")\big)"}],
                    [{"tex": r"g_{\ell_2}(\mathbf{z}) = \dfrac{\mathbf{z}}{\max(\lVert\mathbf{z}\rVert_2,\ 10^{-6})}\qquad\text{or}\qquad g_{\mathrm{LN}},\ g_{\mathrm{id}}"}],
                ],
            },
            {
                "id": "iaei_decode", "title": "Decode reconstruction", "phase": "B - Reconstruct",
                "note": "The decoder maps the latent back to a normalised reconstruction with the same channel count and patch size as the input; this is the reconstruct() forward used at inference, returning both the reconstruction and the latent.",
                "inputs": ["z", "wstar"], "outputs": ["xrecn"],
                "lines": [
                    [{"id": "xrecn", "tex": r"\hat{\mathbf{x}}_n", "role": "intermediate"}, {"tex": "="}, {"tex": r"\mathrm{Dec}_{\theta}\!\big("}, {"id": "z", "tex": r"\mathbf{z}", "role": "intermediate"}, {"tex": r"\big) \in \mathbb{R}^{B\times C_{\mathrm{in}}\times P\times P}"}],
                ],
            },
            {
                "id": "iaei_denorm", "title": "Denormalise to physical units", "phase": "B - Reconstruct",
                "note": "Input and reconstruction are inverted with the same input stats: scale, shift, and for log1p slots (SLC and ifg magnitudes) apply expm1 after clamping the argument to [log1p(floor), log1p(ceil)] with floor 0 and ceil 1000, so error is measured in physical backscatter units.",
                "inputs": ["xn", "xrecn", "stats"], "outputs": ["gt", "pred"],
                "lines": [
                    [{"id": "gt", "tex": r"\mathbf{x}", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathrm{denorm}\!\big("}, {"id": "xn", "tex": r"\hat{\mathbf{x}}", "role": "measured"}, {"tex": r"\big),\quad \mathrm{denorm}(u)_c = \mathrm{expm1}\!\big(\operatorname{clip}(u_c s_c + \mu_c,\ 0,\ \log 1001)\big)\ \ (\mathrm{log1p})"}],
                    [{"id": "pred", "tex": r"\tilde{\mathbf{x}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathrm{denorm}\!\big("}, {"id": "xrecn", "tex": r"\hat{\mathbf{x}}_n", "role": "intermediate"}, {"tex": r"\big),\qquad \text{else } u_c s_c + \mu_c"}],
                ],
            },
            {
                "id": "iaei_embed", "title": "Pool latent to embedding", "phase": "B - Reconstruct",
                "note": "Each patch embedding is the latent averaged over its spatial dimensions (a global mean pool); if the latent is already a vector it passes through, and embeddings are concatenated across every patch of the split.",
                "inputs": ["z"], "outputs": ["emb"],
                "lines": [
                    [{"id": "emb", "tex": r"\bar{\mathbf{z}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{1}{h\,w}\sum_{u,v}"}, {"id": "z", "tex": r"\mathbf{z}_{:,\,:,\,u,v}", "role": "intermediate"}, {"tex": r"\ \in \mathbb{R}^{D}"}],
                ],
            },
            {
                "id": "iaei_residual", "title": "Reconstruction residual", "phase": "C - Metrics",
                "note": "The residual is the elementwise difference between the physical reconstruction and the physical input in float64; every reconstruction metric below is a reduction of it.",
                "inputs": ["pred", "gt"], "outputs": ["err"],
                "lines": [
                    [{"id": "err", "tex": r"e", "role": "intermediate"}, {"tex": "="}, {"id": "pred", "tex": r"\tilde{\mathbf{x}}", "role": "calculated"}, {"tex": "-"}, {"id": "gt", "tex": r"\mathbf{x}", "role": "calculated"}],
                ],
            },
            {
                "id": "iaei_physical", "title": "Physical error metrics", "phase": "C - Metrics",
                "note": "MSE reduces the squared residual over all pixels; R^2 uses the total sum of squares about the global GT mean; PSNR uses the GT dynamic range as the peak. A 1e-8 stabiliser guards both denominators, and PSNR is NaN when the range is zero.",
                "inputs": ["err", "gt"], "outputs": ["mse", "r2", "psnr"],
                "lines": [
                    [{"id": "mse", "tex": r"\mathrm{MSE}", "role": "calculated"}, {"tex": "="}, {"tex": r"\big\langle e^2\big\rangle,\qquad"}, {"id": "r2", "tex": r"R^2", "role": "calculated"}, {"tex": "="}, {"tex": r"1 - \dfrac{\sum e^2}{\sum (\mathbf{x}-\bar{\mathbf{x}})^2 + \varepsilon}"}],
                    [{"id": "psnr", "tex": r"\mathrm{PSNR}", "role": "calculated"}, {"tex": "="}, {"tex": r"10\log_{10}\dfrac{(\max\mathbf{x} - \min\mathbf{x})^2}{\mathrm{MSE} + \varepsilon},\qquad \varepsilon = 10^{-8}"}],
                ],
            },
            {
                "id": "iaei_normalized", "title": "Normalized-space error", "phase": "C - Metrics",
                "note": "To report an error comparable across heavy-tailed channels, the physical GT and prediction are re-normalised with the input stats and their MSE and MAE recomputed in dimensionless units.",
                "inputs": ["pred", "gt", "stats"], "outputs": ["nmse"],
                "lines": [
                    [{"id": "nmse", "tex": r"\mathrm{MSE}_n", "role": "calculated"}, {"tex": "="}, {"tex": r"\Big\langle\big(\mathrm{norm}("}, {"id": "pred", "tex": r"\tilde{\mathbf{x}}", "role": "calculated"}, {"tex": r") - \mathrm{norm}("}, {"id": "gt", "tex": r"\mathbf{x}", "role": "calculated"}, {"tex": r")\big)^2\Big\rangle"}],
                ],
            },
            {
                "id": "iaei_channel", "title": "Per-channel error", "phase": "C - Metrics",
                "note": "Averaging the squared residual over patches and both spatial axes but not the channel axis gives a per-input-channel MSE, isolating which passes or interferograms reconstruct worst.",
                "inputs": ["err"], "outputs": ["cmse"],
                "lines": [
                    [{"id": "cmse", "tex": r"m_c", "role": "calculated"}, {"tex": "="}, {"tex": r"\big\langle e_c^2 \big\rangle_{(p,\,i,\,j)},\qquad c = 1,\dots,C_{\mathrm{in}}"}],
                ],
            },
            {
                "id": "iaei_embstats", "title": "Embedding diagnostics", "phase": "C - Metrics",
                "note": "Three latent-collapse diagnostics: the mean L2 norm of the patch embeddings, the mean per-dimension standard deviation across patches, and the fraction of dimensions whose std exceeds 1e-4 (the active-dimension fraction).",
                "inputs": ["emb"], "outputs": ["estat"],
                "lines": [
                    [{"tex": r"\sigma_d = \operatorname*{std}_p\,"}, {"id": "emb", "tex": r"\bar{z}_{p,d}", "role": "calculated"}, {"tex": r",\qquad \rho_{\mathrm{act}} = \big\langle \mathbb{1}[\sigma_d > 10^{-4}]\big\rangle_d"}],
                    [{"id": "estat", "tex": r"\mathbf{\delta}", "role": "calculated"}, {"tex": "="}, {"tex": r"\big(\ \langle\lVert\bar{\mathbf{z}}_p\rVert_2\rangle_p,\ \ \langle\sigma_d\rangle_d,\ \ \rho_{\mathrm{act}}\ \big)"}],
                ],
            },
            {
                "id": "iaei_persist", "title": "Persist embeddings, metrics, report", "phase": "D - Persist",
                "note": "The stacked embeddings are written to embeddings.npy, the metric dict (with the split name and region) to metrics.json, and a Markdown report is assembled; reconstruction figures (best, worst and random patches, error histogram, per-channel bars, embedding norm) are rendered when save_plots is on.",
                "inputs": ["emb", "mse", "r2", "psnr", "nmse", "cmse", "estat"], "outputs": ["E", "report"],
                "lines": [
                    [{"id": "E", "tex": r"E", "role": "final"}, {"tex": "="}, {"tex": r"\big[\,"}, {"id": "emb", "tex": r"\bar{\mathbf{z}}_1, \dots, \bar{\mathbf{z}}_{N_p}", "role": "calculated"}, {"tex": r"\,\big] \to \texttt{embeddings.npy}"}],
                    [{"id": "report", "tex": r"\mathcal{M}", "role": "final"}, {"tex": "="}, {"tex": r"\{\,\mathrm{MSE},\ R^2,\ \mathrm{PSNR},\ m_c,\ \dots\,\} \to \texttt{metrics.json},\ \texttt{report.md}"}],
                ],
            },
        ]
        return {
            "key"   : "image_ae_infer",
            "name"  : "Image AE (Infer)",
            "blurb" : "Replay a trained image autoencoder over a split. Load the weights, stats and patch loader, encode each normalised patch to a latent and decode it back, denormalise to physical units, then score reconstruction error (MSE, R2, PSNR), latent diagnostics, and persist embeddings, metrics and a report.",
            "nodes" : nodes,
            "steps" : steps,
        }

    def _benchmark(self) -> dict:
        """Returns the flow for equal-capacity architecture benchmarking."""
        nodes = [
            {"id": "models",  "tex": r"\mathcal{M}",      "role": "measured",     "kind": "set",    "shape": "N_m",             "desc": "backbone architectures in the registry to benchmark (skip_models removed)", "sample": ["unet", "resunet", "swin_unet", "segformer"]},
            {"id": "Nstar",   "tex": r"N^{*}",            "role": "calculated",   "kind": "scalar", "shape": "1",               "desc": "reference-model trainable-parameter budget every model is matched to",      "sample": "7,142,912"},
            {"id": "scale",   "tex": r"s",                "role": "intermediate", "kind": "scalar", "shape": "1",               "desc": "width multiplier under the bracketed geometric bisection",                  "sample": "1.02"},
            {"id": "Nk",      "tex": r"N(s)",             "role": "intermediate", "kind": "scalar", "shape": "1",               "desc": "parameter count of the candidate model at scale s",                         "sample": "7,041,220"},
            {"id": "dev",     "tex": r"\delta",           "role": "intermediate", "kind": "scalar", "shape": "1",               "desc": "relative deviation of the candidate count from the budget",                 "sample": "-0.014"},
            {"id": "smatch",  "tex": r"\omega",           "role": "calculated",   "kind": "set",    "shape": "widths",          "desc": "capacity-matched width overrides, rounded to the divisor 8",                "sample": "features=[48, 96, 192, 384]"},
            {"id": "ctx",     "tex": r"C_{\mathrm{ctx}}", "role": "measured",     "kind": "scalar", "shape": "GB",              "desc": "CUDA-context memory already resident on the target device",                 "sample": "0.42"},
            {"id": "peak",    "tex": r"m_b",              "role": "intermediate", "kind": "scalar", "shape": "GB",              "desc": "peak reserved VRAM of a real 3-step train loop at batch b, plus context",   "sample": "31.6"},
            {"id": "bstar",   "tex": r"B^{*}",            "role": "calculated",   "kind": "scalar", "shape": "1",               "desc": "largest power-of-two batch whose footprint stays under the budget",         "sample": "128"},
            {"id": "units",   "tex": r"\mathcal{U}",      "role": "calculated",   "kind": "set",    "shape": "N_m x N_c x N_s", "desc": "(model, loss-component, seed) work units of the benchmark grid",            "sample": ["unet__param_l1_seed0", "resunet__param_l1_seed0"]},
            {"id": "ckpt",    "tex": r"\theta^{\star}",   "role": "calculated",   "kind": "vector", "shape": "|theta|",         "desc": "best-epoch checkpoint per unit at matched width and measured batch",        "sample": ["0.30", "-0.09", "0.17"]},
            {"id": "metrics", "tex": r"\mathbf{q}",       "role": "calculated",   "kind": "vector", "shape": "N_q",             "desc": "per-unit test-split metric vector (curve, parameter, physics)",             "sample": ["0.94", "1.72", "0.08"]},
            {"id": "agg",     "tex": r"\bar{\mathbf{q}}", "role": "calculated",   "kind": "vector", "shape": "N_q",             "desc": "per-model seed-aggregated metric mean (std kept alongside)",                "sample": ["0.94", "1.70", "0.08"]},
            {"id": "board",   "tex": r"\mathcal{S}",      "role": "final",        "kind": "vector", "shape": "N_m",             "desc": "magnitude-aware composite leaderboard score, ranked over models",           "sample": ["unet 0.88", "resunet 0.71"]},
        ]
        steps = [
            {
                "id": "bench_reference", "title": "Reference parameter budget", "phase": "A - Capacity match",
                "note": "The reference model (unet by default) is instantiated at its default width with the fixed in_channels = 9 and the Gaussian-head out_channels, and its total trainable-parameter count becomes the budget every other architecture is scaled to hit.",
                "inputs": ["models"], "outputs": ["Nstar"],
                "lines": [
                    [{"id": "Nstar", "tex": r"N^{*}", "role": "calculated"}, {"tex": "="}, {"tex": r"\sum_{p\,\in\,f_{\mathrm{ref}}} \lvert p\rvert,\qquad f_{\mathrm{ref}} = \mathtt{unet}\big(C_{\mathrm{in}}{=}9,\ C_{\mathrm{out}}\big)"}],
                ],
            },
            {
                "id": "bench_search", "title": "Bracketed bisection on width", "phase": "A - Capacity match",
                "note": "The scale bracket starts at [0.05, 8.0]; the upper bound is doubled (capped at 64) until the widest candidate reaches the budget, then the multiplier is bisected by geometric mean for up to 100 iterations, each candidate instantiated and counted, halving the interval by the sign of the deviation until |delta| <= 5%.",
                "inputs": ["Nstar"], "outputs": ["dev", "scale"],
                "iterative": {"unit": "i", "steps": 100, "symbol": "s",
                              "trace": ["0.63", "2.25", "1.19", "0.87", "1.02", "0.99", "1.00"]},
                "lines": [
                    [{"id": "scale", "tex": r"s", "role": "intermediate"}, {"tex": "="}, {"tex": r"\sqrt{\ell\,h}\,,\qquad"}, {"id": "Nk", "tex": r"N(s)", "role": "intermediate"}, {"tex": r"=\ \textstyle\sum_p \lvert p\rvert\quad\big(\ell,h\ \text{init}\ [0.05,\,8.0],\ \ h\!\leftarrow\!2h\ \text{to}\ 64\big)"}],
                    [{"id": "dev", "tex": r"\delta", "role": "intermediate"}, {"tex": "="}, {"tex": r"\dfrac{"}, {"id": "Nk", "tex": r"N(s)", "role": "intermediate"}, {"tex": r"-\ "}, {"id": "Nstar", "tex": r"N^{*}", "role": "calculated"}, {"tex": r"}{\max(N^{*},1)},\quad \ell\!\leftarrow\!s\ \text{if}\ \delta<0\ \text{else}\ h\!\leftarrow\!s,\ \ \text{stop}\ |\delta|\le 0.05"}],
                ],
            },
            {
                "id": "bench_widths", "title": "Rounded width overrides", "phase": "A - Capacity match",
                "note": "The winning scale becomes concrete width overrides: each scalable attribute (e.g. the UNet features list, divisor 8) is scaled, rounded to its divisor and floored at it, while the locked embedding dims are never touched; a degeneracy audit flags a scale pinned at a search bound or a width clamped at the rounding minimum.",
                "inputs": ["scale"], "outputs": ["smatch"],
                "lines": [
                    [{"id": "smatch", "tex": r"\omega_a", "role": "calculated"}, {"tex": "="}, {"tex": r"\max\!\big(d,\ \operatorname{round}(w_a\,"}, {"id": "scale", "tex": r"s", "role": "intermediate"}, {"tex": r"/d)\cdot d\big),\qquad d = 8\ \ (\mathtt{features})"}],
                    [{"tex": r"a \notin \{\mathtt{embedding\_dim},\ \mathtt{embedding\_dims}\}\quad (\text{locked, unscaled})"}],
                ],
            },
            {
                "id": "bench_context", "title": "CUDA-context baseline", "phase": "B - Max batch",
                "note": "On the target GPU, after clearing the cache, the already-resident memory (total minus free) is taken as the CUDA-context baseline and added to every later peak; above 1.5 GB it warns that another process is co-resident and shrinking the effective budget.",
                "inputs": [], "outputs": ["ctx"],
                "lines": [
                    [{"id": "ctx", "tex": r"C_{\mathrm{ctx}}", "role": "measured"}, {"tex": "="}, {"tex": r"\dfrac{M_{\mathrm{total}} - M_{\mathrm{free}}}{2^{30}},\qquad \text{warn if}\ C_{\mathrm{ctx}} > 1.5\ \mathrm{GB}"}],
                ],
            },
            {
                "id": "bench_probe", "title": "Real-loss memory probe", "phase": "B - Max batch",
                "note": "For each power-of-two batch b up to min(max_batch = 512, |train|), a real 3-step training loop runs at the matched width (bf16 autocast forward, the true composite loss, backward, optimiser step) and its peak reserved memory plus the context is the measured footprint; the surrogate never underestimates like an MSE probe would.",
                "inputs": ["smatch", "ctx"], "outputs": ["peak"],
                "lines": [
                    [{"id": "peak", "tex": r"m_b", "role": "intermediate"}, {"tex": "="}, {"id": "ctx", "tex": r"C_{\mathrm{ctx}}", "role": "measured"}, {"tex": r"+\ \dfrac{1}{2^{30}}\,\operatorname{maxreserved}\!\big(f_{"}, {"id": "smatch", "tex": r"\omega", "role": "calculated"}, {"tex": r"},\,b\big),\quad b\in\{1,2,4,\dots,\min(512,\,|\mathrm{train}|)\}"}],
                ],
            },
            {
                "id": "bench_maxbatch", "title": "Largest batch under budget", "phase": "B - Max batch",
                "note": "The largest batch whose footprint stays at or below the VRAM budget (40 GB) is kept; the scan halts at the first over-budget or OOM batch, and a model that cannot fit batch 1 fails loudly rather than training at an unfair size.",
                "inputs": ["peak"], "outputs": ["bstar"],
                "lines": [
                    [{"id": "bstar", "tex": r"B^{*}", "role": "calculated"}, {"tex": "="}, {"tex": r"\max\big\{\,b :\ "}, {"id": "peak", "tex": r"m_b", "role": "intermediate"}, {"tex": r"\ \le\ V_{\mathrm{budget}}\,\big\},\qquad V_{\mathrm{budget}} = 40\ \mathrm{GB}"}],
                    [{"tex": r"\text{halt at first OVER / OOM};\qquad"}, {"id": "peak", "tex": r"m_1", "role": "intermediate"}, {"tex": r"> V_{\mathrm{budget}} \Rightarrow \mathtt{FAIL}"}],
                ],
            },
            {
                "id": "bench_units", "title": "Benchmark grid expansion", "phase": "C - Sweep grid",
                "note": "The grid is the Cartesian product of architectures, swept loss components (default {param_l1}) and seeds; with no seeds each (model, component) pair is a single unit, otherwise every pair is repeated per seed as model__component_seed{s}.",
                "inputs": ["models"], "outputs": ["units"],
                "lines": [
                    [{"id": "units", "tex": r"\mathcal{U}", "role": "calculated"}, {"tex": "="}, {"id": "models", "tex": r"\mathcal{M}", "role": "measured"}, {"tex": r"\times\ \mathcal{C}\ \times\ \mathcal{S},\qquad \mathcal{C} = \{\mathtt{param\_l1}\}\ \ (\text{default})"}],
                    [{"tex": r"\mathrm{name} = m \,\Vert\, c\ [\,\mathrm{seed}\,s\,],\qquad \mathcal{S} = \varnothing \Rightarrow N_s = 1"}],
                ],
            },
            {
                "id": "bench_train", "title": "Train each unit", "phase": "D - Train & infer",
                "note": "Every unit is trained by the standard backbone pipeline at its matched width and measured max batch, with the loss curriculum pinned to that unit's single component; best-epoch weights are checkpointed. Architectures thus differ only in inductive bias, not in capacity or batch size.",
                "inputs": ["units", "smatch", "bstar"], "outputs": ["ckpt"],
                "lines": [
                    [{"id": "ckpt", "tex": r"\theta^{\star}_u", "role": "calculated"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,min}_{\mathrm{epoch}}\ \mathcal{L}_{\mathrm{val}}\big(f_{"}, {"id": "smatch", "tex": r"\omega", "role": "calculated"}, {"tex": r",\,c};\ \mathrm{batch}{=}"}, {"id": "bstar", "tex": r"B^{*}", "role": "calculated"}, {"tex": r"\big),\quad u \in "}, {"id": "units", "tex": r"\mathcal{U}", "role": "calculated"}],
                ],
            },
            {
                "id": "bench_infer", "title": "Infer on the test split", "phase": "D - Train & infer",
                "note": "Each trained unit runs the standard sliding-window inference on the held-out test split, producing the full scalar metric suite per unit: curve errors, parameter errors and physics-consistency measures.",
                "inputs": ["ckpt"], "outputs": ["metrics"],
                "lines": [
                    [{"id": "metrics", "tex": r"\mathbf{q}_u", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathrm{Metrics}\big(f_{"}, {"id": "ckpt", "tex": r"\theta^{\star}_u", "role": "calculated"}, {"tex": r"}(\mathbf{X}_{\mathrm{test}})\big)"}],
                ],
            },
            {
                "id": "bench_aggregate", "title": "Aggregate over seeds", "phase": "E - Compare",
                "note": "Units sharing a model base are grouped and their per-seed metrics reduced to a mean and standard deviation (the checkpoint best-val-loss too), so seed noise is separated from genuine architecture differences.",
                "inputs": ["metrics"], "outputs": ["agg"],
                "lines": [
                    [{"id": "agg", "tex": r"\bar{\mathbf{q}}_m", "role": "calculated"}, {"tex": "="}, {"tex": r"\operatorname*{mean}_{s}\ "}, {"id": "metrics", "tex": r"\mathbf{q}_{m,s}", "role": "calculated"}, {"tex": r",\qquad \sigma_m = \operatorname*{std}_{s}\ "}, {"id": "metrics", "tex": r"\mathbf{q}_{m,s}", "role": "calculated"}],
                ],
            },
            {
                "id": "bench_leaderboard", "title": "Composite-score leaderboard", "phase": "E - Compare",
                "note": "Each headline metric is min-max normalised across models to [0, 1] (1 = best by its own direction, missing metrics score 0) and averaged into a magnitude-aware composite Score; models are ranked by Score, with mean rank, wins and the gap Delta to the leader reported.",
                "inputs": ["agg"], "outputs": ["board"],
                "lines": [
                    [{"id": "board", "tex": r"\mathrm{Score}_m", "role": "final"}, {"tex": "="}, {"tex": r"\dfrac{1}{|Q|}\sum_{q\in Q}\ \operatorname{minmax}_q\!\big("}, {"id": "agg", "tex": r"\bar{q}_{m,q}", "role": "calculated"}, {"tex": r"\big)\ \in [0,1]"}],
                    [{"tex": r"\text{rank by Score},\qquad \Delta_m ="}, {"id": "board", "tex": r"\mathrm{Score}_m", "role": "final"}, {"tex": r"\ -\ \max_{m'}\mathrm{Score}_{m'}\ \le 0"}],
                ],
            },
        ]
        return {
            "key"   : "benchmark",
            "name"  : "Benchmark (Capacity-matched)",
            "blurb" : "Fair architecture comparison at equal capacity. Every backbone is scaled to the reference model's parameter budget by bracketed bisection, given its own largest batch that fits the VRAM budget under a real 3-step training probe, then trained and inferred identically across a (model, loss-component, seed) grid; seeds are aggregated and models ranked by a magnitude-aware composite score.",
            "nodes" : nodes,
            "steps" : steps,
        }

    def _cross_validate(self) -> dict:
        """Returns the flow for guarded K-fold spatial cross-validation."""
        nodes = [
            {"id": "cv_extent",     "tex": r"\Omega_{\mathrm{az}}", "role": "measured",     "kind": "set",    "shape": "(az0, az1)", "desc": "fold azimuth window in absolute SLC lines",               "sample": "(1000, 16000)"},
            {"id": "cv_guard",      "tex": r"g",                    "role": "measured",     "kind": "scalar", "shape": "1",          "desc": "guard-band width between folds (azimuth lines, even)",    "sample": "64"},
            {"id": "cv_blocks",     "tex": r"B_k",                  "role": "calculated",   "kind": "set",    "shape": "K x 2",      "desc": "K equal-width contiguous azimuth blocks",                 "sample": [["1000", "2500"], ["2500", "4000"]]},
            {"id": "cv_region",     "tex": r"R_k",                  "role": "calculated",   "kind": "set",    "shape": "A_z x R_g",  "desc": "guard-trimmed block region (azimuth slice x full range)", "sample": "[2532, 3968) x [0, 3000)"},
            {"id": "cv_split",      "tex": r"\Omega^{(k)}",         "role": "calculated",   "kind": "set",    "shape": "3 regions",  "desc": "fold-k disjoint train / val / test split regions",        "sample": "test B0, val B1, train B2..9"},
            {"id": "cv_units",      "tex": r"\mathcal{U}",          "role": "calculated",   "kind": "set",    "shape": "K x |S|",    "desc": "expanded (fold, seed) training run units",                "sample": ["fold_0", "fold_1", "..."]},
            {"id": "cv_model",      "tex": r"\theta_k^{\star}",     "role": "intermediate", "kind": "tensor", "shape": "|theta|",    "desc": "fold-k best-epoch weights and validation loss",           "sample": "0.041 (best val)"},
            {"id": "cv_metrics",    "tex": r"m_k^{(s)}",            "role": "calculated",   "kind": "set",    "shape": "n_m",        "desc": "per-fold, per-split inference metric set",                "sample": ["0.12", "0.19", "0.86"]},
            {"id": "cv_foldmetric", "tex": r"\bar{m}_k^{(s)}",      "role": "calculated",   "kind": "vector", "shape": "n_m",        "desc": "per-fold seed-aggregated metric (seed mean, seed std)",   "sample": "0.12, sd 0.01"},
            {"id": "cv_agg",        "tex": r"\bar{m}^{(s)}",        "role": "final",        "kind": "vector", "shape": "n_m",        "desc": "cross-fold aggregate: mean and sample std (ddof=1)",      "sample": "0.13, sd 0.02"},
            {"id": "cv_report",     "tex": r"\mathcal{R}",          "role": "final",        "kind": "set",    "shape": "files",      "desc": "aggregate report, summary JSON, per-split comparisons",   "sample": "cv_aggregate_report.md, cv_summary.json"},
        ]
        steps = [
            {
                "id": "cv_partition", "title": "Azimuth block partition", "phase": "A - Fold plan",
                "note": "The fold azimuth window [azimuth_start, azimuth_end) (default [1000, 16000)) is cut into K = n_folds contiguous equal-width blocks of size floor((az1-az0)/K); the final block absorbs the remainder. K must be at least 3 so that train, val and test stay mutually disjoint.",
                "inputs": ["cv_extent"], "outputs": ["cv_blocks"],
                "lines": [
                    [{"tex": r"w = \big\lfloor (\mathtt{az}_1 - \mathtt{az}_0)/K \big\rfloor,\qquad K = n_{\mathrm{folds}} \ge 3"}],
                    [{"id": "cv_blocks", "tex": r"B_k", "role": "calculated"}, {"tex": "="}, {"tex": r"\big[\,\mathtt{az}_0 + k\,w,\ \ \mathtt{az}_0 + (k{+}1)\,w\,\big),\qquad"}, {"id": "cv_extent", "tex": r"\Omega_{\mathrm{az}} = [\mathtt{az}_0, \mathtt{az}_1)", "role": "measured"}],
                ],
            },
            {
                "id": "cv_guard", "title": "Guard-band trimming", "phase": "A - Fold plan",
                "note": "Interior block boundaries are eroded by margin = guard/2 lines on each side, while outer edges at the window boundary are left intact; this opens a guard-width gap between neighbouring splits so no patch straddles two folds. guard (default 64) must be even, non-negative and strictly smaller than the smallest block.",
                "inputs": ["cv_blocks", "cv_guard"], "outputs": ["cv_region"],
                "lines": [
                    [{"id": "cv_region", "tex": r"R_k", "role": "calculated"}, {"tex": "="}, {"tex": r"\big[\,s_k + m\,\mathbb{1}_{s_k>\mathtt{az}_0},\ \ e_k - m\,\mathbb{1}_{e_k<\mathtt{az}_1}\,\big)\ \times\ [\mathtt{rg}_0, \mathtt{rg}_1)"}],
                    [{"tex": r"m = "}, {"id": "cv_guard", "tex": r"g", "role": "measured"}, {"tex": r"/2,\qquad g\ \text{even},\quad 0 \le g < \min_k \big|"}, {"id": "cv_blocks", "tex": r"B_k", "role": "calculated"}, {"tex": r"\big|"}],
                ],
            },
            {
                "id": "cv_assign", "title": "Fold role assignment", "phase": "A - Fold plan",
                "note": "For fold k the test band is block k and the validation band is the next block (k+1) mod K; the remaining K-2 blocks form the training set, with adjacent blocks merged into contiguous regions. Rotating k over 0..K-1 yields K disjoint train / val / test partitions of the same scene.",
                "inputs": ["cv_region"], "outputs": ["cv_split"],
                "lines": [
                    [{"id": "cv_split", "tex": r"\Omega^{(k)}", "role": "calculated"}, {"tex": r":\quad \mathrm{test} = "}, {"id": "cv_region", "tex": r"R_k", "role": "calculated"}, {"tex": r",\quad \mathrm{val} = R_{(k+1)\bmod K}"}],
                    [{"tex": r"\mathrm{train} = \mathrm{merge}\big\{\,R_j : j \notin \{\,k,\ (k{+}1)\bmod K\,\}\,\big\}"}],
                ],
            },
            {
                "id": "cv_units", "title": "Seed replication", "phase": "B - Fold training",
                "note": "Each fold is one run; supplying a seed list replicates every fold once per seed (run name fold_k_seedS) so per-fold seed dispersion can be measured, otherwise a single unseeded run per fold. All fold x seed units are queued across the configured GPUs and resumed when a checkpoint already exists.",
                "inputs": ["cv_split"], "outputs": ["cv_units"],
                "lines": [
                    [{"id": "cv_units", "tex": r"\mathcal{U}", "role": "calculated"}, {"tex": "="}, {"tex": r"\{\,\mathrm{fold}\_k : k < K\,\}\ \times\ \mathcal{S},\qquad |\mathcal{U}| = K\cdot\max(|\mathcal{S}|,\,1)"}],
                    [{"tex": r"\mathcal{S} = \emptyset:\ \ \texttt{fold\_k}\ \ (\text{unseeded})\qquad \mathcal{S} \ne \emptyset:\ \ \texttt{fold\_k\_seed}s"}],
                ],
            },
            {
                "id": "cv_train", "title": "Per-fold training", "phase": "B - Fold training",
                "note": "Every unit trains an independent backbone / JEPA / autoencoder pipeline on its fold's train and val regions as a GPU job, recording the best-epoch checkpoint and its validation loss; the guard band keeps each fold's training region disjoint from its held-out val and test bands, so the per-fold validation loss is a leakage-free generalisation estimate.",
                "inputs": ["cv_units", "cv_split"], "outputs": ["cv_model"],
                "iterative": {"var": "L*", "steps": 10, "unit": "fold", "symbol": r"L^{\star}",
                              "trace": ["4.1e-2", "3.8e-2", "5.2e-2", "4.4e-2", "3.9e-2"]},
                "lines": [
                    [{"id": "cv_model", "tex": r"\theta_k^{\star}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\arg\min_{\theta}\ \mathcal{L}_{\mathrm{val}}\big(\theta;\ "}, {"id": "cv_split", "tex": r"\Omega^{(k)}", "role": "calculated"}, {"tex": r"\big)"}],
                    [{"tex": r"L_k^{\star} = \mathcal{L}_{\mathrm{val}}(\theta_k^{\star}),\qquad k = 0,\dots,K-1"}],
                ],
            },
            {
                "id": "cv_infer", "title": "Per-fold-split inference", "phase": "C - Fold inference",
                "note": "Unless the model is a profile autoencoder (those folds are scored by reconstruction loss alone), each trained fold is inferred on its held-out val and test bands into a per-fold, per-split metric set. Each fold's val and test bands are single contiguous blocks, which is what cube stitching requires; a split is skipped only when its inference already completed under resume.",
                "inputs": ["cv_model", "cv_split"], "outputs": ["cv_metrics"],
                "lines": [
                    [{"id": "cv_metrics", "tex": r"m_k^{(s)}", "role": "calculated"}, {"tex": "="}, {"tex": r"\mathcal{M}\big(f_{"}, {"id": "cv_model", "tex": r"\theta_k^{\star}", "role": "intermediate"}, {"tex": r"};\ \Omega^{(k)}_s\big),\qquad s \in \{\texttt{val},\ \texttt{test}\}"}],
                    [{"tex": r"\text{skip if}\ m_k^{(s)}\ \text{already complete (resume) or no checkpoint}"}],
                ],
            },
            {
                "id": "cv_collect", "title": "Seed aggregation per fold", "phase": "D - Aggregation",
                "note": "Runs are regrouped by fold; a fold with several seed replicas is reduced to the across-seed mean and the within-fold seed standard deviation per metric, contributing one representative record. With no seed sweep this is a pass-through.",
                "inputs": ["cv_metrics"], "outputs": ["cv_foldmetric"],
                "lines": [
                    [{"id": "cv_foldmetric", "tex": r"\bar{m}_k^{(s)}", "role": "calculated"}, {"tex": "="}, {"tex": r"\tfrac{1}{|\mathcal{S}_k|}\sum_{j}\,"}, {"id": "cv_metrics", "tex": r"m_{k,j}^{(s)}", "role": "calculated"}, {"tex": r",\qquad \sigma_k^{\mathrm{seed}} = \operatorname{std}_{j}\,m_{k,j}^{(s)}"}],
                ],
            },
            {
                "id": "cv_aggregate", "title": "Cross-fold mean and std", "phase": "D - Aggregation",
                "note": "Each metric is averaged over the folds that produced a finite value, with the sample standard deviation (ddof = 1) reported only when at least 2 folds contributed; before aggregating, the report asserts all K folds trained (hold a checkpoint) and every fold has metrics on each split.",
                "inputs": ["cv_foldmetric"], "outputs": ["cv_agg"],
                "lines": [
                    [{"id": "cv_agg", "tex": r"\bar{m}^{(s)}", "role": "final"}, {"tex": "="}, {"tex": r"\tfrac{1}{N}\sum_{k \in F}\,"}, {"id": "cv_foldmetric", "tex": r"\bar{m}_k^{(s)}", "role": "calculated"}, {"tex": r",\quad F = \{\,k : \bar{m}_k^{(s)}\ \text{finite}\,\}"}],
                    [{"tex": r"\hat{\sigma}^{(s)} = \sqrt{\tfrac{1}{N-1}\sum_{k \in F}\big(\bar{m}_k^{(s)} - \bar{m}^{(s)}\big)^2}\,,\qquad N = |F| \ge 2"}],
                ],
            },
            {
                "id": "cv_report", "title": "Aggregate report and summary", "phase": "D - Aggregation",
                "note": "The fold plan, an across-fold training summary (best epoch, best val loss, duration) and grouped metric aggregate tables are written to cv_aggregate_report.md; cv_summary.json carries every mean, std and per-fold value machine-readably; and per-split comparison reports are emitted with fold ranking disabled.",
                "inputs": ["cv_agg"], "outputs": ["cv_report"],
                "lines": [
                    [{"id": "cv_report", "tex": r"\mathcal{R}", "role": "final"}, {"tex": "="}, {"tex": r"\big\{\ \texttt{cv\_aggregate\_report.md},\ \ \texttt{cv\_summary.json},\ \ \{\texttt{val},\texttt{test}\}/\ \big\}"}],
                ],
            },
        ]
        return {
            "key"   : "cross_validate",
            "name"  : "Cross-Validation (K-fold)",
            "blurb" : "K-fold spatial cross-validation. Partition the scene azimuth into K equal blocks, erode a guard band so folds cannot leak, and rotate each block through test / val / train; train one model per fold (optionally per seed), infer on the held-out val and test bands, then aggregate every metric into a cross-fold mean and sample standard deviation with a machine-readable summary.",
            "nodes" : nodes,
            "steps" : steps,
        }

    def _tuning(self) -> dict:
        """Returns the flow for the joint Optuna hyperparameter study."""
        nodes = [
            {"id": "space",     "tex": r"\Theta",                 "role": "measured",     "kind": "set",    "shape": "-", "desc": "joint learning, regularisation and architecture search space", "sample": ["lr", "wd", "features", "..."]},
            {"id": "theta_lr",  "tex": r"\theta_{\mathrm{lr}}",   "role": "intermediate", "kind": "vector", "shape": "9", "desc": "4 group LRs, 4 group weight decays, dropout",                  "sample": ["2.6e-4", "8e-5", "...", "0.12"]},
            {"id": "theta_ar",  "tex": r"\theta_{\mathrm{arch}}", "role": "intermediate", "kind": "vector", "shape": "5", "desc": "features, bottleneck factor, activation, norm, upsample",      "sample": ["[64,128,256,512]", "2", "gelu", "group", "bilinear"]},
            {"id": "theta",     "tex": r"\theta",                 "role": "intermediate", "kind": "vector", "shape": "d", "desc": "sampled joint hyperparameter vector",                          "sample": ["3e-4", "1e-4", "64", "..."]},
            {"id": "ell",       "tex": r"\ell(\theta)",           "role": "calculated",   "kind": "scalar", "shape": "1", "desc": "TPE good-trial KDE density at theta",                          "sample": "4.7"},
            {"id": "g",         "tex": r"g(\theta)",              "role": "calculated",   "kind": "scalar", "shape": "1", "desc": "TPE bad-trial KDE density at theta",                           "sample": "0.9"},
            {"id": "acq",       "tex": r"a(\theta)",              "role": "calculated",   "kind": "scalar", "shape": "1", "desc": "TPE acquisition = good-over-bad density ratio",                "sample": "5.2"},
            {"id": "liar",      "tex": r"\tilde{y}",              "role": "intermediate", "kind": "scalar", "shape": "1", "desc": "constant-liar phantom objective for pending trials",           "sample": "2.9e-2"},
            {"id": "cfg",       "tex": r"\mathcal{C}_t",          "role": "intermediate", "kind": "set",    "shape": "-", "desc": "per-trial config with budget, patience and seed overrides",    "sample": ["E=30", "pat=8", "seed=42+t"]},
            {"id": "fobj",      "tex": r"f(\theta)",              "role": "calculated",   "kind": "scalar", "shape": "1", "desc": "trial objective: minimum validation loss over the budget",     "sample": "2.3e-2"},
            {"id": "med",       "tex": r"m^{(t)}",                "role": "calculated",   "kind": "scalar", "shape": "1", "desc": "running median of completed-trial losses at step t",           "sample": "3.4e-2"},
            {"id": "rem",       "tex": r"n_{\mathrm{rem}}",       "role": "intermediate", "kind": "scalar", "shape": "1", "desc": "remaining trials to dispatch across GPUs",                     "sample": "36"},
            {"id": "thetastar", "tex": r"\theta^{*}",             "role": "final",        "kind": "vector", "shape": "d", "desc": "best joint configuration, decoded and exported",               "sample": ["2.6e-4", "8e-5", "96", "..."]},
        ]
        steps = [
            {
                "id": "spacelr", "title": "Learning and regularisation space", "phase": "Search space",
                "note": "The lr block declares four per-group learning rates and four weight decays as log-uniform floats, plus dropout as a linear-uniform float.",
                "inputs": [], "outputs": ["theta_lr"],
                "lines": [
                    [{"id": "theta_lr", "tex": r"\eta_{\{\mathrm{enc,bot,dec,head}\}}", "role": "intermediate"}, {"tex": r"\sim \log\mathcal{U}(10^{-5},10^{-2}),\quad \lambda_{\{\cdot\}} \sim \log\mathcal{U}(10^{-6},10^{-1})"}],
                    [{"tex": r"p_{\mathrm{drop}} \sim \mathcal{U}(0,\,0.5)"}],
                ],
            },
            {
                "id": "spacearch", "title": "Architecture space", "phase": "Search space",
                "note": "Five categorical hyperparameters; the list-valued features channel is stored as an integer index and decoded back to its list on export.",
                "inputs": [], "outputs": ["theta_ar"],
                "lines": [
                    [{"id": "theta_ar", "tex": r"\mathbf{w}", "role": "intermediate"}, {"tex": r"= C[\,k\,],\quad k\sim\mathcal{U}\{0,\dots,3\}"}],
                    [{"tex": r"b\in\{1,2,4\},\ \ \sigma\in\{\mathrm{relu,lrelu,gelu,silu}\},\ \ \mathrm{norm}\in\{\mathrm{batch,inst,group}\},\ \ \mathrm{up}\in\{\mathrm{tconv,bilin}\}"}],
                ],
            },
            {
                "id": "merge", "title": "Joint space", "phase": "Search space",
                "note": "The two blocks are merged into one joint space; TPE with multivariate sampling models the cross-dependencies directly.",
                "inputs": ["theta_lr", "theta_ar"], "outputs": ["space"],
                "lines": [
                    [{"id": "space", "tex": r"\Theta", "role": "measured"}, {"tex": "="}, {"tex": r"\Theta_{\mathrm{lr}} \times \Theta_{\mathrm{arch}},\qquad d = |\Theta| = 14"}],
                ],
            },
            {
                "id": "tpesplit", "title": "TPE density split", "phase": "Joint search",
                "note": "Once the startup trials exist, TPE splits observed trials by the gamma-quantile of their objective into a good set (low loss) and a bad set, fitting a KDE to each.",
                "inputs": ["fobj", "space"], "outputs": ["ell", "g"],
                "lines": [
                    [{"id": "ell", "tex": r"\ell(\theta)", "role": "calculated"}, {"tex": r"= p(\theta \mid f(\theta) \le y_\gamma),\qquad"}, {"id": "g", "tex": r"g(\theta)", "role": "calculated"}, {"tex": r"= p(\theta \mid f(\theta) > y_\gamma)"}],
                    [{"tex": r"y_\gamma = \inf\{\,y : P(f(\theta) \le y) \ge \gamma\,\}"}],
                ],
            },
            {
                "id": "tpeacq", "title": "Density-ratio proposal", "phase": "Joint search",
                "note": "TPE proposes the candidate maximising the good-over-bad density ratio (equivalent to expected improvement); for the first startup trials it samples uniformly instead.",
                "inputs": ["ell", "g", "space"], "outputs": ["acq", "theta"],
                "lines": [
                    [{"id": "acq", "tex": r"a(\theta)", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{"}, {"id": "ell", "tex": r"\ell(\theta)", "role": "calculated"}, {"tex": r"}{"}, {"id": "g", "tex": r"g(\theta)", "role": "calculated"}, {"tex": r"}"}],
                    [{"id": "theta", "tex": r"\theta", "role": "intermediate"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,max}_{\theta\in\Theta}\ a(\theta)\quad(\text{after } n_0 = 8 \text{ startup trials})"}],
                ],
            },
            {
                "id": "liar", "title": "Constant-liar parallelism", "phase": "Joint search",
                "note": "With many GPU workers sharing one SQLite study, each pending trial is temporarily assigned the worst completed objective so concurrent workers do not all propose the same point.",
                "inputs": ["fobj"], "outputs": ["liar"],
                "lines": [
                    [{"id": "liar", "tex": r"\tilde{y}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\max_{j\in\mathcal{C}} f(\theta_j)\quad \forall\,\theta_i\in\mathcal{R}\ (\text{pending})"}],
                    [{"tex": r"\mathrm{seed}_{\mathrm{sampler}} = 42 + \mathrm{gpu\_id}"}],
                ],
            },
            {
                "id": "trialsetup", "title": "Trial isolation and overrides", "phase": "Trial & pruning",
                "note": "Each objective deep-copies the base trainer and dataset configs and overrides the epoch budget, scheduler horizon, early-stop patience, per-trial log dir and seed, keyed on the global trial number.",
                "inputs": ["theta"], "outputs": ["cfg"],
                "lines": [
                    [{"tex": r"\mathrm{setattr}("}, {"id": "cfg", "tex": r"\mathcal{C}_t", "role": "intermediate"}, {"tex": r", k, v)\quad \forall (k,v)\in"}, {"id": "theta", "tex": r"\theta", "role": "intermediate"}],
                    [{"tex": r"E_{\mathrm{trial}} = 30,\quad \mathrm{patience} = 8,\quad \mathrm{seed} = 42 + \mathrm{trial.number}"}],
                ],
            },
            {
                "id": "trial", "title": "Trial objective", "phase": "Trial & pruning",
                "note": "Each trial trains a full model on the fixed canonical split and returns the minimum validation loss over the epoch budget, capped earlier by early stopping or pruning.",
                "inputs": ["cfg"], "outputs": ["fobj"],
                "iterative": {"var": "fobj", "steps": 30, "unit": "epoch", "symbol": "f",
                              "trace": ["6.0e-2", "4.1e-2", "3.0e-2", "2.5e-2", "2.3e-2"]},
                "lines": [
                    [{"id": "fobj", "tex": r"f(\theta)", "role": "calculated"}, {"tex": "="}, {"tex": r"\min_{e \in \{1,\dots,E\}}\ \mathcal{L}^{(e)}_{\mathrm{val}}\!\big("}, {"id": "cfg", "tex": r"\mathcal{C}_t", "role": "intermediate"}, {"tex": r"\big),\quad E = 30"}],
                ],
            },
            {
                "id": "prune", "title": "Median pruning with gates", "phase": "Trial & pruning",
                "note": "A trial is pruned at step t once its best reported loss exceeds the running median of completed-trial losses, but only after 8 startup trials and once t clears the 8-step warmup. Pruned trials count toward the budget; stale running trials are marked FAIL on resume.",
                "inputs": ["fobj"], "outputs": ["med"],
                "lines": [
                    [{"id": "med", "tex": r"m^{(t)}", "role": "calculated"}, {"tex": "="}, {"tex": r"\operatorname{median}\big\{\,"}, {"id": "fobj", "tex": r"f^{(t)}_j", "role": "calculated"}, {"tex": r": j \in \mathrm{COMPLETE}\,\big\}"}],
                    [{"tex": r"\mathrm{prune} \iff \mathcal{L}^{(t)}_{\mathrm{val}} > "}, {"id": "med", "tex": r"m^{(t)}", "role": "calculated"}, {"tex": r"\ \wedge\ n_{\mathrm{complete}} \ge 8\ \wedge\ t \ge 8"}],
                ],
            },
            {
                "id": "best", "title": "Chunked top-up and argmin export", "phase": "Best-config export",
                "note": "The study counts done trials and dispatches only the remaining ones across GPUs in chunks; the best config is rewritten after every completed trial, decoding the features index back to its list.",
                "inputs": ["fobj"], "outputs": ["rem", "thetastar"],
                "lines": [
                    [{"id": "rem", "tex": r"n_{\mathrm{rem}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\max\!\big(0,\ N - n_{\mathrm{done}}\big),\qquad N = 100"}],
                    [{"id": "thetastar", "tex": r"\theta^{*}", "role": "final"}, {"tex": "="}, {"tex": r"\operatorname*{arg\,min}_{\theta \in \Theta}\ "}, {"id": "fobj", "tex": r"f(\theta)", "role": "calculated"}],
                ],
            },
        ]
        return {
            "key": "tuning", "name": "Tuning (Optuna)",
            "blurb": "A single joint Optuna study wraps the training pipeline: an explicit log-uniform and categorical search space, TPE density-ratio proposals with constant-liar parallelism, gated median pruning, and the best joint configuration exported, resumable in chunks.",
            "nodes": nodes, "steps": steps,
        }

    def _feed_tuner(self) -> dict:
        """Returns the flow for sweeping DataLoader settings against the real workload."""
        nodes = [
            {"id": "dset",    "tex": r"\mathcal{D}",          "role": "measured",     "kind": "set",    "shape": "N",             "desc": "real training dataset from the mode's adapter (same items as training)", "sample": "profiles, len 96"},
            {"id": "model",   "tex": r"f_\theta",             "role": "measured",     "kind": "tensor", "shape": "params",        "desc": "the mode's real model plus AdamW step; the GPU workload",                "sample": "mlp_ae"},
            {"id": "bset",    "tex": r"\mathcal{B}",          "role": "measured",     "kind": "vector", "shape": "n_b",           "desc": "batch-size sweep grid (samples)",                                        "sample": ["256", "512", "1024", "2048", "4096"]},
            {"id": "wset",    "tex": r"\mathcal{W}",          "role": "measured",     "kind": "vector", "shape": "n_w",           "desc": "DataLoader worker-count sweep grid",                                     "sample": ["0", "2", "4", "6", "8"]},
            {"id": "pset",    "tex": r"\mathcal{P}",          "role": "measured",     "kind": "vector", "shape": "n_p",           "desc": "prefetch-factor sweep grid",                                             "sample": ["2", "4", "8", "16"]},
            {"id": "tau",     "tex": r"\tau_w",               "role": "measured",     "kind": "scalar", "shape": "1",             "desc": "data-wait target (GPU-idle fraction)",                                   "sample": "0.05"},
            {"id": "spec",    "tex": r"\ell",                 "role": "intermediate", "kind": "set",    "shape": "(b,w,p,pin)",   "desc": "one loader configuration (batch, workers, prefetch, pin)",               "sample": "(1024, 4, 4, pin)"},
            {"id": "tload",   "tex": r"R_{\mathrm{load}}",    "role": "intermediate", "kind": "scalar", "shape": "1",             "desc": "loader-only throughput, GPU idle (samples/s)",                           "sample": "82000"},
            {"id": "tgpu",    "tex": r"R_{\mathrm{gpu}}",     "role": "intermediate", "kind": "scalar", "shape": "1",             "desc": "GPU compute ceiling on one reused batch (samples/s)",                    "sample": "95000"},
            {"id": "te2e",    "tex": r"R_{\mathrm{e2e}}",     "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "end-to-end training throughput (samples/s)",                             "sample": "78000"},
            {"id": "wait",    "tex": r"w_{\mathrm{d}}",       "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "data-wait fraction, GPU-idle share of a step",                           "sample": "0.03"},
            {"id": "util",    "tex": r"u_{\mathrm{gpu}}",     "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "mean GPU utilization over the run (%)",                                  "sample": "91"},
            {"id": "fr",      "tex": r"\phi",                 "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "feed ratio, loader over ceiling (dimensionless)",                        "sample": "0.86"},
            {"id": "eff",     "tex": r"\eta",                 "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "compute efficiency, end-to-end over ceiling",                            "sample": "0.82"},
            {"id": "rec",     "tex": r"\mathbf{r}",           "role": "calculated",   "kind": "set",    "shape": "per spec",      "desc": "per-spec result record",                                                 "sample": ["1024", "4", "78000", "0.03"]},
            {"id": "sat",     "tex": r"\mathcal{S}",          "role": "calculated",   "kind": "set",    "shape": "subset",        "desc": "GPU-saturated configuration subset",                                     "sample": "{bs1024/w4, ...}"},
            {"id": "cpub",    "tex": r"\beta_{\mathrm{cpu}}", "role": "calculated",   "kind": "scalar", "shape": "1",             "desc": "CPU-bound flag (saturated set empty)",                                   "sample": "False"},
            {"id": "reco",    "tex": r"\ell^\star",           "role": "final",        "kind": "set",    "shape": "(b,w,...)",     "desc": "recommended loader configuration",                                       "sample": "bs=1024, w=4"},
            {"id": "refbest", "tex": r"\rho^\star",           "role": "calculated",   "kind": "set",    "shape": "(p,pin)",       "desc": "best prefetch and pin from the refine sweep",                            "sample": "(8, pin)"},
            {"id": "final",   "tex": r"\ell^\dagger",         "role": "final",        "kind": "set",    "shape": "(b,w,p,pin,+)", "desc": "final DataLoader configuration written to results",                      "sample": "bs1024 w4 pf8 pin1"},
            {"id": "results", "tex": r"\mathcal{J}",          "role": "final",        "kind": "set",    "shape": "json + figs",   "desc": "results.json plus four diagnostic figures",                              "sample": "results.json + 4 png"},
        ]
        steps = [
            {
                "id": "feed_target", "title": "Feed target assembly", "phase": "A - Target",
                "note": "The adapter selected by mode (default profile_autoencoder) builds the actual training dataset and model plus a real forward/backward/AdamW step, so the measured CPU item cost and GPU compute match production; the loss is reconstruction MSE for the autoencoder modes and MSE against zero for the backbone.",
                "inputs": [], "outputs": ["model", "dset"],
                "lines": [
                    [{"tex": r"\big("}, {"id": "dset", "tex": r"\mathcal{D}", "role": "measured"}, {"tex": r",\ "}, {"id": "model", "tex": r"f_\theta", "role": "measured"}, {"tex": r"\big) = \mathrm{Adapter}_{\texttt{mode}}()"}],
                    [{"tex": r"\texttt{mode}\in\{\texttt{synthetic},\ \texttt{profile\_autoencoder},\ \texttt{image\_autoencoder},\ \texttt{backbone}\},\quad \mathcal{L} = \mathrm{MSE}(\mathrm{rec}_\theta(x),\,x)\ \ \text{or}\ \ \mathrm{MSE}(f_\theta(x),\,\mathbf{0})"}],
                ],
            },
            {
                "id": "feed_grid", "title": "Main sweep grid", "phase": "B - Sweep grid",
                "note": "The main sweep enumerates every (batch, workers) pair with the reference prefetch factor 4, pin-memory on and persistent workers on; worker counts above the machine core count C are dropped. The default grid is 5 batch sizes times up to 5 worker counts, run one spec at a time.",
                "inputs": ["bset", "wset"], "outputs": ["spec"],
                "iterative": {"unit": "spec", "steps": 25, "symbol": r"\ell",
                              "trace": ["31k", "58k", "74k", "78k", "61k"]},
                "lines": [
                    [{"id": "spec", "tex": r"\ell", "role": "intermediate"}, {"tex": r"\in \big\{(b,\,w,\,p_0,\,\text{pin}) :\ "}, {"id": "bset", "tex": r"b\in\mathcal{B}", "role": "measured"}, {"tex": r",\ "}, {"id": "wset", "tex": r"w\in\mathcal{W}", "role": "measured"}, {"tex": r",\ w\le C\big\}"}],
                    [{"tex": r"\mathcal{B} = \{256,512,1024,2048,4096\},\quad \mathcal{W} = \{0,2,4,6,8\},\quad p_0 = 4"}],
                ],
            },
            {
                "id": "feed_loader", "title": "Loader-only throughput", "phase": "C - Per-spec probe",
                "note": "With no GPU work the loader alone is iterated for 8 warm-up then 60 timed batches (shuffle and drop_last on, one thread per worker); the pure data-pipeline throughput is the samples produced over wall time.",
                "inputs": ["dset", "spec"], "outputs": ["tload"],
                "lines": [
                    [{"id": "tload", "tex": r"R_{\mathrm{load}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\dfrac{n_t\,b}{t_{\mathrm{load}}},\qquad n_{\mathrm{wu}} = 8,\ \ n_t = 60\ \ (\text{GPU idle})"}],
                ],
            },
            {
                "id": "feed_ceiling", "title": "GPU compute ceiling", "phase": "C - Per-spec probe",
                "note": "One batch is moved to the GPU and pushed through the real train step 60 times (after 8 warm-up), CUDA-synchronised; reusing a single batch removes all data cost, so this is the pure GPU compute ceiling. AdamW lr is 1e-4 and AMP, when on, uses bf16 (off by default).",
                "inputs": ["model", "spec"], "outputs": ["tgpu"],
                "lines": [
                    [{"id": "tgpu", "tex": r"R_{\mathrm{gpu}}", "role": "intermediate"}, {"tex": "="}, {"tex": r"\dfrac{n_t\,b}{t_{\mathrm{gpu}}},\qquad x_0\ \text{reused every step}"}],
                    [{"tex": r"\theta \leftarrow \theta - \mathrm{AdamW}\!\big(\nabla_\theta\,"}, {"id": "model", "tex": r"\mathcal{L}(f_\theta, x_0)", "role": "measured"}, {"tex": r"\big),\quad \mathrm{lr} = 10^{-4}"}],
                ],
            },
            {
                "id": "feed_e2e", "title": "End-to-end split", "phase": "C - Per-spec probe",
                "note": "The real loop times each batch's fetch-wait t_d and its compute t_c separately; the end-to-end rate divides by their sum and the data-wait fraction is the share the GPU idles waiting for data. A background nvml thread samples utilisation every 50 ms.",
                "inputs": ["dset", "model", "spec"], "outputs": ["te2e", "util", "wait"],
                "lines": [
                    [{"id": "te2e", "tex": r"R_{\mathrm{e2e}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{n_t\,b}{t_d + t_c},\qquad"}, {"id": "wait", "tex": r"w_{\mathrm{d}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{t_d}{t_d + t_c}"}],
                    [{"id": "util", "tex": r"u_{\mathrm{gpu}}", "role": "calculated"}, {"tex": "="}, {"tex": r"\big\langle \mathrm{util}_{\mathrm{nvml}}(t)\big\rangle,\qquad \Delta t_s = 50\,\mathrm{ms}"}],
                ],
            },
            {
                "id": "feed_ratios", "title": "Derived feed ratios", "phase": "C - Per-spec probe",
                "note": "The record's feed ratio is loader capacity over the GPU ceiling (>= 1 means the CPU can outpace the GPU) and efficiency is the achieved rate over that ceiling; out-of-memory specs are caught and recorded as failed rather than aborting the sweep.",
                "inputs": ["tload", "tgpu", "te2e"], "outputs": ["fr", "eff", "rec"],
                "lines": [
                    [{"id": "fr", "tex": r"\phi", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{"}, {"id": "tload", "tex": r"R_{\mathrm{load}}", "role": "intermediate"}, {"tex": r"}{"}, {"id": "tgpu", "tex": r"R_{\mathrm{gpu}}", "role": "intermediate"}, {"tex": r"},\qquad"}, {"id": "eff", "tex": r"\eta", "role": "calculated"}, {"tex": "="}, {"tex": r"\dfrac{"}, {"id": "te2e", "tex": r"R_{\mathrm{e2e}}", "role": "calculated"}, {"tex": r"}{"}, {"id": "tgpu", "tex": r"R_{\mathrm{gpu}}", "role": "intermediate"}, {"tex": r"}"}],
                    [{"id": "rec", "tex": r"\mathbf{r}", "role": "calculated"}, {"tex": r"= \big(\ell,\ R_{\mathrm{load}},\ R_{\mathrm{gpu}},\ R_{\mathrm{e2e}},\ "}, {"id": "wait", "tex": r"w_{\mathrm{d}}", "role": "calculated"}, {"tex": r",\ u_{\mathrm{gpu}},\ \phi,\ \eta\big)"}],
                ],
            },
            {
                "id": "feed_saturate", "title": "GPU-saturated set", "phase": "D - Recommendation",
                "note": "A config is GPU-saturated when its data-wait is at or below the target 0.05 or its feed ratio reaches 1; if none qualify the saturated set is empty and the run is flagged CPU-bound, and the full ok set is used for the pick instead.",
                "inputs": ["rec", "tau"], "outputs": ["sat", "cpub"],
                "lines": [
                    [{"id": "sat", "tex": r"\mathcal{S}", "role": "calculated"}, {"tex": r"= \big\{\mathbf{r} :\ "}, {"id": "wait", "tex": r"w_{\mathrm{d}}", "role": "calculated"}, {"tex": r"\le"}, {"id": "tau", "tex": r"\tau_w", "role": "measured"}, {"tex": r"\ \ \lor\ \ "}, {"id": "fr", "tex": r"\phi", "role": "calculated"}, {"tex": r"\ge 1\big\},\qquad \tau_w = 0.05"}],
                    [{"id": "cpub", "tex": r"\beta_{\mathrm{cpu}}", "role": "calculated"}, {"tex": r"= \big[\,"}, {"id": "sat", "tex": r"\mathcal{S}", "role": "calculated"}, {"tex": r"= \varnothing\,\big]"}],
                ],
            },
            {
                "id": "feed_recommend", "title": "Best configuration", "phase": "D - Recommendation",
                "note": "Within the saturated pool (or the whole ok set when CPU-bound) the highest end-to-end throughput wins, ties breaking toward fewer workers then smaller batch; if no spec ran successfully the pipeline raises SystemExit.",
                "inputs": ["sat"], "outputs": ["reco"],
                "lines": [
                    [{"id": "reco", "tex": r"\ell^\star", "role": "final"}, {"tex": r"= \arg\!\max_{\mathbf{r}\in "}, {"id": "sat", "tex": r"\mathcal{S}", "role": "calculated"}, {"tex": r"}\ \mathrm{lex}\big("}, {"id": "te2e", "tex": r"R_{\mathrm{e2e}}\!\downarrow", "role": "calculated"}, {"tex": r",\ w\!\uparrow,\ b\!\uparrow\big)"}],
                    [{"tex": r"\text{pool} = "}, {"id": "sat", "tex": r"\mathcal{S}", "role": "calculated"}, {"tex": r"\ \text{if}\ \neg"}, {"id": "cpub", "tex": r"\beta_{\mathrm{cpu}}", "role": "calculated"}, {"tex": r"\ \text{else all ok};\quad \mathcal{S}_{\mathrm{ok}} = \varnothing \Rightarrow \texttt{SystemExit}"}],
                ],
            },
            {
                "id": "feed_refine", "title": "Prefetch and pin refine", "phase": "E - Refine",
                "note": "Enabled by default: holding the recommended batch and at-least-one workers fixed, a second sweep varies prefetch over {2,4,8,16} and pin-memory on/off, and its highest-throughput row is kept.",
                "inputs": ["reco", "pset"], "outputs": ["refbest"],
                "lines": [
                    [{"tex": r"\mathcal{G}_{\mathrm{ref}} = \big\{(b^\star,\ \max(1,w^\star),\ p,\ \mathrm{pin}) :\ "}, {"id": "pset", "tex": r"p\in\mathcal{P}", "role": "measured"}, {"tex": r",\ \mathrm{pin}\in\{0,1\}\big\}"}],
                    [{"id": "refbest", "tex": r"\rho^\star", "role": "calculated"}, {"tex": r"= (p^\star,\mathrm{pin}^\star) = \arg\!\max_{\mathcal{G}_{\mathrm{ref}}}\ "}, {"id": "te2e", "tex": r"R_{\mathrm{e2e}}", "role": "calculated"}, {"tex": r",\qquad \mathcal{P} = \{2,4,8,16\}"}],
                ],
            },
            {
                "id": "feed_final", "title": "Final configuration", "phase": "E - Refine",
                "note": "The final config takes batch and workers from the recommendation and, when the refine sweep produced results, overrides prefetch and pin-memory with its best row; otherwise they default to prefetch 4 and pin on. The cpu-bound flag is carried through.",
                "inputs": ["reco", "refbest", "cpub"], "outputs": ["final"],
                "lines": [
                    [{"id": "final", "tex": r"\ell^\dagger", "role": "final"}, {"tex": r"= \big(b^\star,\ w^\star,\ "}, {"id": "refbest", "tex": r"\rho^\star", "role": "calculated"}, {"tex": r",\ \text{persist},\ "}, {"id": "cpub", "tex": r"\beta_{\mathrm{cpu}}", "role": "calculated"}, {"tex": r"\big)"}],
                    [{"tex": r"\rho^\star \leftarrow (4,\ \text{pin on})\quad\text{if the refine sweep is empty}"}],
                ],
            },
            {
                "id": "feed_report", "title": "Results and figures", "phase": "F - Report",
                "note": "The main and refine sweeps, the recommendation and the final config are written to results.json, and four diagnostic figures are saved when save_figures is on and the ok frame is non-empty.",
                "inputs": ["rec", "reco", "final"], "outputs": ["results"],
                "lines": [
                    [{"id": "results", "tex": r"\mathcal{J}", "role": "final"}, {"tex": r"= \big\{\text{main},\ \text{refine},\ "}, {"id": "reco", "tex": r"\ell^\star", "role": "final"}, {"tex": r",\ "}, {"id": "final", "tex": r"\ell^\dagger", "role": "final"}, {"tex": r"\big\} \to \texttt{results.json}"}],
                    [{"tex": r"\text{figures}:\ R_{\mathrm{e2e}}\text{-vs-}b,\ \ w_{\mathrm{d}}\text{-vs-}w,\ \ u_{\mathrm{gpu}}\text{-vs-}R_{\mathrm{e2e}},\ \ \phi\text{-vs-}w"}],
                ],
            },
        ]
        return {
            "key"   : "feed_tuner",
            "name"  : "Feed Tuner (DataLoader)",
            "blurb" : "Sweep DataLoader settings against the real training workload. The mode's adapter wires the actual dataset and model plus a genuine forward/backward/AdamW step, then per (batch, workers) spec the benchmark measures loader-only throughput, the GPU compute ceiling on one reused batch, and the end-to-end rate with its data-wait fraction and GPU utilisation; the highest-throughput GPU-saturated config is picked (fewer workers, smaller batch as tie-breakers), a second sweep refines prefetch and pin-memory, and the final DataLoader configuration with four diagnostic figures is written.",
            "nodes" : nodes,
            "steps" : steps,
        }

    def collect(self) -> list:
        """Returns every flow definition in presentation order."""
        return [
            self._processing(),
            self._param_extraction(),
            self._dataset(),
            self._training(),
            self._dual_train(),
            self._profile_ae_train(),
            self._image_ae_train(),
            self._jepa_train(),
            self._unrolled_train(),
            self._inference(),
            self._profile_ae_infer(),
            self._image_ae_infer(),
            self._benchmark(),
            self._cross_validate(),
            self._tuning(),
            self._feed_tuner(),
        ]
