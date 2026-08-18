"""Curated flow diagrams describing the processing pipeline for the web UI.

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
            {"id": "Tcomb",  "tex": r"T_{\mathrm{comb}}",     "role": "final",        "kind": "tensor", "shape": "H x A_z x R_g",   "desc": "combined beamformed tomogram over the full azimuth crop",           "sample": [["0.2", "0.9", "0.3"], ["0.1", "0.7", "0.8"], ["0.0", "0.4", "1.0"]]},
            {"id": "DEM",    "tex": r"D",                     "role": "final",        "kind": "matrix", "shape": "A_z x R_g",       "desc": "full-stack concatenated DEM (m)",                                        "sample": [["31.2", "30.8"], ["32.1", "31.5"]]},
            {"id": "stilde", "tex": r"\tilde{s}_i",           "role": "intermediate", "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "DEM-deramped secondary SLC",                                             "sample": [["0.6+0.1j", "0.5-0.1j"], ["0.7+0.2j", "0.6-0.0j"]]},
            {"id": "cross",  "tex": r"c_i",                   "role": "intermediate", "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "raw master-secondary cross-product",                                     "sample": [["0.45+0.30j", "0.41-0.12j"], ["0.55+0.18j", "0.48-0.05j"]]},
            {"id": "pi",     "tex": r"p_i",                   "role": "intermediate", "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "unit-magnitude interferometric phasor",                                  "sample": [["0.83+0.55j", "0.96-0.28j"], ["0.95+0.31j", "0.99-0.10j"]]},
            {"id": "Ai",     "tex": r"A_i",                   "role": "intermediate", "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "clipped secondary amplitude weight",                                     "sample": [["0.71", "0.93"], ["1.25", "0.58"]]},
            {"id": "phii",   "tex": r"\tilde{\phi}_i",        "role": "final",        "kind": "tensor", "shape": "N_s x A_z x R_g", "desc": "amplitude-weighted complex interferogram (interferometric stack)",               "sample": [["0.51+0.20j", "0.44-0.12j"], ["0.63+0.18j", "0.55-0.05j"]]},
            {"id": "bv",     "tex": r"b^{\mathrm{v}}_i",      "role": "calculated",   "kind": "vector", "shape": "N_p",             "desc": "vertical baseline relative to reference pass (m)",                       "sample": ["0.00", "12.4", "-8.1", "20.7"]},
            {"id": "bh",     "tex": r"b^{\mathrm{h}}_i",      "role": "calculated",   "kind": "vector", "shape": "N_p",             "desc": "horizontal baseline relative to reference pass (m)",                     "sample": ["0.00", "5.2", "-3.4", "9.8"]},
            {"id": "prof",   "tex": r"\mathbf{\tau}_i",       "role": "calculated",   "kind": "tensor", "shape": "N_p x A_z",       "desc": "per-azimuth horizontal/vertical track position profiles (m)",            "sample": [["112.3", "112.5"], ["101.7", "101.9"]]},
            {"id": "look",   "tex": r"\theta",                "role": "calculated",   "kind": "vector", "shape": "R_g",             "desc": "per-range look angle theta (rad)",                                       "sample": ["0.79", "0.80", "...", "1.02"]},
            {"id": "brel",   "tex": r"\mathbf{\beta}_i",      "role": "calculated",   "kind": "tensor", "shape": "N_p x A_z",       "desc": "reference-relative baseline profiles, horizontal & vertical (m)",        "sample": [["0.00", "0.00"], ["5.2", "4.9"]]},
            {"id": "geom",   "tex": r"k_z",                   "role": "final",        "kind": "tensor", "shape": "N_p x A_z x R_g", "desc": "per-pixel interferometric wavenumber k_z (rad/m) geometry field",  "sample": [["0.00", "0.00"], ["0.11", "0.12"]]},
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
                "note": "The worker HDF5 files are reassembled along azimuth into the full-stack products: the 2-D DEM concatenates on axis 0 and the 3-D tomogram on axis 1, then both are saved as .npy.",
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
                "note": "Re-attaching the clipped amplitude as the phasor's modulus gives an interferogram whose phase is the residual (sub-DEM) elevation phase and whose magnitude is a bounded signal-strength proxy; this stack is the run's interferometric product.",
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
                "note": "The perpendicular baseline projects the horizontal and vertical baselines onto the look direction, and the interferometric wavenumber (default height convention, dividing by r sin theta) is stored per (pass, azimuth, range) as the geometry-field artifact; the reference pass has zero baseline, so its kz vanishes.",
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
            "blurb" : "From the F-SAR SLC passes to the reference tomogram and the interferometric stack. Each azimuth subsection is Capon-beamformed by a PyRat FuSARtomo worker and reassembled; the co-registered secondaries are DEM-deramped and amplitude-weighted into the interferometric stack; and the track geometry becomes a per-pixel wavenumber field.",
            "nodes" : nodes,
            "steps" : steps,
        }

    def collect(self) -> list:
        """Returns every flow definition in presentation order."""
        return [
            self._processing(),
        ]
