"use strict";

class FlowSketches {

  static pulse(svg, gsap) {
    if (!gsap) return null;

    const els = svg.querySelectorAll(".sk-live");
    if (!els.length) return null;

    return gsap.to(els, { opacity: 0.35, duration: 1.25, ease: "sine.inOut", repeat: -1, yoyo: true, stagger: { each: 0.16, from: "start" } });
  }

  static grid(cells, build) {
    let out = "";
    for (let r = 0; r < cells; r++) for (let c = 0; c < cells; c++) out += build(r, c);
    return out;
  }

  static CATALOG = {

  subdivide: {
    tip: "Crops above W_max = 1000 lines split into M azimuth subsections, run by a worker plan from budget B = floor(0.8 C).",
    build(svg) { svg.innerHTML = `
      <rect x="40" y="30" width="38" height="104" rx="2" class="skl-pop f-meas" style="opacity:.8"/>
      <text x="108" y="80" text-anchor="middle" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect x="134" y="30" width="76" height="22" rx="2" class="skl-pop f-mid"/>
      <rect x="134" y="56" width="76" height="22" rx="2" class="skl-pop f-mid"/>
      <rect x="134" y="82" width="76" height="22" rx="2" class="skl-pop f-mid"/>
      <rect x="134" y="108" width="76" height="22" rx="2" class="skl-pop f-mid"/>
      <circle class="sk-live skl-pop f-cal" cx="146" cy="41" r="3"/>
      <circle class="sk-live skl-pop f-cal" cx="146" cy="67" r="3"/>
      <circle class="sk-live skl-pop f-cal" cx="146" cy="93" r="3"/>
      <circle class="sk-live skl-pop f-cal" cx="146" cy="119" r="3"/>`; },
    anim: FlowSketches.pulse,
  },

  covariance: {
    tip: "Inside a PyRat FuSARtomo worker a 20x10 boxcar averages the SLC passes into the sample covariance R-hat.",
    build(svg) {
      const m = FlowSketches.grid(4, (r, c) => {
        const x = 92 + c * 26, y = 34 + r * 26;
        const cl = r === c ? "sk-live skl-pop f-cal" : (Math.abs(r - c) === 1 ? "skl-pop f-mid" : "skl-pop f-faint");
        const op = r === c ? 1 : (Math.abs(r - c) === 1 ? 0.5 : 0.28);
        return `<rect class="${cl}" x="${x}" y="${y}" width="22" height="22" rx="2" style="opacity:${op}"/>`;
      });
      svg.innerHTML = `
        <rect x="36" y="50" width="34" height="20" rx="2" class="skl-draw c-mid" style="fill:none"/>
        <text x="53" y="84" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">boxcar</text>
        ${m}
        <text x="143" y="126" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">R-hat</text>`;
    },
    anim: FlowSketches.pulse,
  },

  capon: {
    tip: "FuSARtomo's Capon estimator 1/(a^H R^-1 a) beamforms over the height range [-20, 80] m and peaks at each scatterer.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="36" y1="120" x2="212" y2="120"/>
      <path class="skl-draw c-cal" d="M36 116 L74 113 L104 108 L124 56 L144 108 L176 114 L212 117" style="fill:none"/>
      <line class="skl-dash c-faint" x1="124" y1="56" x2="124" y2="120"/>
      <circle class="sk-live skl-pop f-fin" cx="124" cy="56" r="4"/>
      <text x="196" y="116" text-anchor="end" style="fill:#7e8aa0;font-size:7px">xi (m)</text>`; },
    anim: FlowSketches.pulse,
  },

  concat: {
    tip: "Worker subsections reassemble along azimuth: DEM on axis 0, tomogram on axis 1.",
    build(svg) { svg.innerHTML = `
      <rect x="44" y="34" width="58" height="20" rx="2" class="skl-pop f-cal"/>
      <rect x="44" y="58" width="58" height="20" rx="2" class="skl-pop f-cal"/>
      <rect x="44" y="82" width="58" height="20" rx="2" class="skl-pop f-cal"/>
      <rect x="44" y="106" width="58" height="20" rx="2" class="skl-pop f-cal"/>
      <text x="120" y="84" text-anchor="middle" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect x="150" y="34" width="58" height="92" rx="3" class="skl-draw c-fin" style="fill:rgba(196,163,255,0.1)"/>
      <text x="179" y="138" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">T_comb</text>`; },
    anim: null,
  },

  slc_load: {
    tip: "Master is an RGI-SLC; each secondary is a co-registered INF-SLC carrying its DEM-predicted phase.",
    build(svg) { svg.innerHTML = `
      <rect x="34" y="36" width="50" height="80" rx="3" class="skl-pop f-meas"/>
      <text x="59" y="128" text-anchor="middle" style="fill:#6ea8ff;font-size:8px">master</text>
      <rect x="150" y="28" width="46" height="74" rx="3" class="skl-pop f-meas" style="opacity:.4"/>
      <rect x="142" y="36" width="46" height="74" rx="3" class="skl-pop f-meas" style="opacity:.6"/>
      <rect x="134" y="44" width="46" height="74" rx="3" class="skl-pop f-meas" style="opacity:.85"/>
      <text x="160" y="128" text-anchor="middle" style="fill:#6ea8ff;font-size:8px">secondaries</text>
      <path class="skl-dash c-mid" d="M86 76 C106 64 116 62 132 74" style="fill:none"/>`; },
    anim: null,
  },

  baselines: {
    tip: "Track positions are averaged over the azimuth window and referenced to track 0; the profiles feed the geometry field.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="40" y1="116" x2="206" y2="116"/>
      <line class="skl-axis" x1="40" y1="116" x2="40" y2="28"/>
      <circle cx="40" cy="100" r="4" class="skl-pop f-faint"/>
      <text x="40" y="132" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">ref</text>
      <line class="skl-dash c-cal" x1="40" y1="100" x2="92" y2="68"/>
      <line class="skl-dash c-cal" x1="40" y1="100" x2="138" y2="90"/>
      <line class="skl-dash c-cal" x1="40" y1="100" x2="186" y2="46"/>
      <circle class="sk-live skl-pop f-cal" cx="92" cy="68" r="4"/>
      <circle class="sk-live skl-pop f-cal" cx="138" cy="90" r="4"/>
      <circle class="sk-live skl-pop f-cal" cx="186" cy="46" r="4"/>`; },
    anim: FlowSketches.pulse,
  },

  deramp: {
    tip: "Multiplying by exp(j phi_DEM) cancels the terrain ramp, leaving only sub-resolution structure.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="120" x2="214" y2="120"/>
      <line class="skl-dash c-faint" x1="28" y1="112" x2="150" y2="46"/>
      <path class="skl-draw c-meas" d="M28 100 q12 -12 24 0 t24 0 t24 0 t24 0 t24 0" style="fill:none"/>
      <text x="76" y="36" style="fill:#7e8aa0;font-size:7px">DEM ramp</text>
      <path class="skl-draw c-cal" d="M28 88 q14 -12 28 0 t28 0 t28 0 t28 0 t28 0 t14 0" transform="translate(0 24)" style="fill:none"/>
      <text x="150" y="118" style="fill:#4fd6c4;font-size:7px">flat residual</text>`; },
    anim: null,
  },

  crossprod: {
    tip: "Conjugating the secondary against the master subtracts its phase and removes phi_DEM from arg(c_i).",
    build(svg) { svg.innerHTML = `
      <circle cx="120" cy="78" r="44" class="skl-axis" style="fill:none;opacity:.5"/>
      <line class="skl-axis" x1="68" y1="78" x2="172" y2="78"/>
      <line class="skl-axis" x1="120" y1="30" x2="120" y2="126"/>
      <line class="skl-draw c-meas" x1="120" y1="78" x2="143" y2="41"/>
      <circle cx="143" cy="41" r="3.2" class="skl-pop f-meas"/>
      <text x="147" y="40" style="fill:#6ea8ff;font-size:8px">s0</text>
      <line class="skl-draw c-mid" x1="120" y1="78" x2="165" y2="71"/>
      <circle cx="165" cy="71" r="3.2" class="skl-pop f-mid"/>
      <text x="169" y="80" style="fill:#f5b971;font-size:8px">s_i*</text>
      <path class="skl-draw c-cal" d="M147.6 73.6 A28 28 0 0 0 134.8 54.3" style="fill:none;stroke-width:1.6"/>
      <text x="150" y="60" style="fill:#4fd6c4;font-size:8px">c_i</text>`; },
    anim: null,
  },

  phasor: {
    tip: "Dividing by |c_i| (floor 1e-30) maps each cross-product onto the unit circle; nulls go to zero, not NaN.",
    build(svg) { svg.innerHTML = `
      <circle cx="120" cy="76" r="46" class="skl-axis" style="fill:none;opacity:.55"/>
      <line class="skl-axis" x1="66" y1="76" x2="174" y2="76"/>
      <line class="skl-axis" x1="120" y1="26" x2="120" y2="126"/>
      <line x1="120" y1="76" x2="150" y2="58" style="stroke:#4a5a6b;stroke-width:1.4"/>
      <circle cx="150" cy="58" r="3" class="skl-pop f-faint"/>
      <line class="sk-live skl-draw c-cal" x1="120" y1="76" x2="159" y2="53" style="opacity:1"/>
      <circle class="sk-live skl-pop f-cal" cx="159" cy="53" r="3.6" style="opacity:1"/>
      <text x="150" y="44" style="fill:#4fd6c4;font-size:8px">|c| = 1</text>`; },
    anim: FlowSketches.pulse,
  },

  clip: {
    tip: "Amplitude is capped at c_max = 1.25 so one bright reflector cannot dominate the per-pass weight.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="214" y2="118"/>
      <line class="sk-live skl-pop" x1="30" y1="56" x2="214" y2="56" style="stroke:#c4a3ff;stroke-width:1.4;stroke-dasharray:4 4;opacity:1"/>
      <text x="210" y="50" text-anchor="end" style="fill:#c4a3ff;font-size:8px">c_max</text>
      <rect x="46" y="90" width="18" height="28" class="skl-pop f-mid"/>
      <rect x="74" y="76" width="18" height="42" class="skl-pop f-mid"/>
      <rect x="102" y="56" width="18" height="62" class="skl-pop f-mid"/>
      <rect x="130" y="98" width="18" height="20" class="skl-pop f-mid"/>
      <rect x="158" y="56" width="18" height="62" class="skl-pop f-mid"/>
      <rect x="186" y="82" width="18" height="36" class="skl-pop f-mid"/>`; },
    anim: FlowSketches.pulse,
  },

  interf: {
    tip: "Clipped A_i re-attaches as the phasor modulus: phase is residual elevation, magnitude a bounded SNR proxy.",
    build(svg) { svg.innerHTML = `
      <circle cx="120" cy="76" r="40" class="skl-axis" style="fill:none;opacity:.5"/>
      <line class="skl-axis" x1="72" y1="76" x2="168" y2="76"/>
      <line class="skl-axis" x1="120" y1="30" x2="120" y2="122"/>
      <text x="120" y="30" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">A_i</text>
      <line class="skl-draw c-cal" x1="120" y1="76" x2="153" y2="54"/>
      <circle cx="153" cy="54" r="3.5" class="skl-pop f-cal"/>
      <path class="skl-dash c-mid" d="M141 76 A21 21 0 0 0 137 64" style="fill:none"/>
      <text x="148" y="66" style="fill:#f5b971;font-size:8px">phi</text>
      <text x="120" y="118" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">A_i &#8736; phi</text>`; },
    anim: null,
  },

  trackgeo: {
    tip: "Look angle theta = arccos((h0-terrain)/r) per range bin; track profiles become baselines relative to the reference pass.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="46" y1="122" x2="212" y2="122"/>
      <circle cx="58" cy="36" r="4" class="skl-pop f-faint"/>
      <text x="58" y="28" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">sensor</text>
      <line class="skl-dash c-faint" x1="58" y1="36" x2="58" y2="122"/>
      <line class="skl-draw c-cal" x1="58" y1="36" x2="182" y2="122"/>
      <text x="128" y="74" style="fill:#4fd6c4;font-size:8px">r</text>
      <path class="sk-live skl-draw c-cal" d="M58 64 A28 28 0 0 1 80 52" style="fill:none;stroke-width:1.5"/>
      <text x="66" y="58" style="fill:#4fd6c4;font-size:8px">&#952;</text>
      <circle class="skl-pop f-cal" cx="182" cy="122" r="3.5"/>
      <text x="152" y="116" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">terrain</text>`; },
    anim: FlowSketches.pulse,
  },

  geomfield: {
    tip: "Perpendicular baseline and kz = (4pi/lambda) b_perp/(r sin theta) give each pixel its own wavenumber; the reference pass is 0.",
    build(svg) {
      const cells = FlowSketches.grid(4, (r, c) => {
        const x = 96 + c * 24, y = 40 + r * 18;
        const op = (0.3 + 0.13 * (r + c)).toFixed(2);
        return `<rect class="sk-live skl-pop f-cal" x="${x}" y="${y}" width="20" height="15" rx="1.5" style="opacity:${op}"/>`;
      });
      svg.innerHTML = `
        <rect x="46" y="34" width="150" height="84" rx="3" class="skl-draw c-fin" style="fill:none"/>
        <rect x="52" y="40" width="34" height="70" rx="2" class="skl-pop f-faint" style="opacity:.35"/>
        <text x="69" y="128" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">ref = 0</text>
        ${cells}
        <text x="132" y="30" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">k_z(a, r)</text>`;
    },
    anim: FlowSketches.pulse,
  },

  threshold: {
    tip: "Samples below t_f = 0.25 x peak are zeroed and bins past H_tr = 170 dropped before the fit sees the profile.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="120" x2="214" y2="120"/>
      <line class="skl-dash c-mid" x1="24" y1="96" x2="180" y2="96"/>
      <text x="26" y="92" style="fill:#f5b971;font-size:7px">floor</text>
      <line class="skl-dash c-faint" x1="180" y1="22" x2="180" y2="122"/>
      <text x="184" y="32" style="fill:#7e8aa0;font-size:7px">H_tr</text>
      <path class="skl-draw c-meas" d="M24 118 L52 70 L64 104 L98 44 L114 100 L150 78 L168 106 L186 90 L204 86" style="fill:none;opacity:.28"/>
      <path class="skl-draw c-cal" d="M24 120 L52 70 L64 104 L82 120 L98 44 L114 100 L132 120 L150 78 L168 120 L180 120" style="fill:none"/>`; },
    anim: null,
  },

  activity: {
    tip: "A profile is fitted only if its peak clears tau_a = 1e-3; otherwise skipped with zero parameters.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="118" x2="214" y2="118"/>
      <line class="skl-dash c-mid" x1="24" y1="58" x2="214" y2="58"/>
      <text x="26" y="52" style="fill:#f5b971;font-size:7px">tau_a</text>
      <path class="skl-draw c-cal" d="M40 118 L52 110 L66 44 L80 112 L92 118" style="fill:none"/>
      <circle cx="66" cy="44" r="4" class="skl-pop f-cal"/>
      <path class="skl-draw c-faint" d="M150 118 L162 112 L176 88 L190 113 L202 118" style="fill:none;opacity:.5"/>
      <circle cx="176" cy="88" r="4" class="skl-pop f-faint"/>
      <text x="176" y="78" text-anchor="middle" style="fill:#4a5a6b;font-size:8px">skip</text>`; },
    anim: null,
  },

  pnorm: {
    tip: "Dividing by the per-profile max sets the tallest peak to one, making the loss comparable across pixels.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="120" x2="214" y2="120"/>
      <line class="skl-axis" x1="24" y1="22" x2="24" y2="120"/>
      <line class="skl-dash c-cal" x1="24" y1="40" x2="214" y2="40"/>
      <text x="208" y="36" text-anchor="end" style="fill:#4fd6c4;font-size:7px">1.0</text>
      <path class="skl-draw c-faint" d="M24 116 L60 96 L96 70 L120 56 L150 92 L188 110 L214 114" style="fill:none;opacity:.4"/>
      <path class="skl-draw c-cal" d="M24 112 L60 78 L96 40 L120 40 L150 84 L188 110 L214 116" style="fill:none"/>`; },
    anim: null,
  },

  peakfind: {
    tip: "find_peaks keeps a maximum only if its prominence reaches p_frac = 0.05 of the peak and it sits d_min bins from rivals.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="120" x2="214" y2="120"/>
      <path class="skl-draw c-meas" d="M24 118 L44 96 L60 40 L78 102 L96 110 L114 70 L132 104 L150 112 L168 58 L190 104 L214 116" style="fill:none"/>
      <circle class="sk-live skl-pop f-cal" cx="60" cy="40" r="4.5"/>
      <circle class="sk-live skl-pop f-cal" cx="168" cy="58" r="4.5"/>
      <circle cx="114" cy="70" r="4" class="skl-pop f-faint"/>`; },
    anim: FlowSketches.pulse,
  },

  geometry: {
    tip: "sigma0 = sigma_base / D_sigma (D_sigma = 4) seeds the width; Adam later clamps it between one bin and half the span.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="40" y1="120" x2="40" y2="24"/>
      <line class="skl-dash c-cal" x1="34" y1="40" x2="200" y2="40"/>
      <text x="46" y="36" style="fill:#4fd6c4;font-size:7px">sigma_hi = span/2</text>
      <line class="skl-dash c-meas" x1="34" y1="108" x2="200" y2="108"/>
      <text x="46" y="120" style="fill:#6ea8ff;font-size:7px">sigma_lo = 1 bin</text>
      <path class="skl-draw c-mid" d="M126 116 q44 -76 88 0" style="fill:none"/>
      <line class="skl-draw c-mid" x1="148" y1="80" x2="192" y2="80" style="stroke-width:1.4"/>
      <text x="158" y="74" style="fill:#f5b971;font-size:8px">sigma0</text>`; },
    anim: null,
  },

  residfill: {
    tip: "If fewer than K peaks are found, each is masked over half-width d_min and the rest filled by repeated argmax.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="118" x2="214" y2="118"/>
      <rect x="32" y="22" width="32" height="96" class="skl-pop f-faint" style="opacity:.4"/>
      <rect x="92" y="22" width="32" height="96" class="skl-pop f-faint" style="opacity:.4"/>
      <path class="skl-draw c-meas" d="M24 116 L48 70 L66 100 L86 84 L108 50 L130 96 L150 78 L172 104 L196 66 L214 110" style="fill:none;opacity:.45"/>
      <circle cx="48" cy="70" r="4" class="skl-pop f-cal"/>
      <circle cx="108" cy="50" r="4" class="skl-pop f-cal"/>
      <circle cx="196" cy="66" r="4.5" class="skl-pop f-mid"/>
      <text x="196" y="56" text-anchor="middle" style="fill:#f5b971;font-size:7px">argmax</text>`; },
    anim: null,
  },

  seed: {
    tip: "Amplitude and mean are read off the peaks as the seed; frozen in sigma mode, refined only when the mode frees them.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="118" x2="214" y2="118"/>
      <path class="skl-draw c-meas" d="M24 116 L52 100 L78 44 L104 102 L130 110 L158 60 L190 104 L214 112" style="fill:none;opacity:.45"/>
      <line class="skl-dash c-cal" x1="78" y1="44" x2="78" y2="118"/>
      <line class="skl-draw c-cal" x1="62" y1="44" x2="94" y2="44" style="stroke-width:1.6"/>
      <circle cx="78" cy="44" r="4" class="skl-pop f-cal"/>
      <line class="skl-dash c-cal" x1="158" y1="60" x2="158" y2="118"/>
      <line class="skl-draw c-cal" x1="142" y1="60" x2="174" y2="60" style="stroke-width:1.6"/>
      <circle cx="158" cy="60" r="4" class="skl-pop f-cal"/>
      <text x="118" y="132" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">a, mu seed</text>`; },
    anim: null,
  },

  objective: {
    tip: "sigma is always fit (amp/mu per mode); the loss is the MSE between the K-Gaussian sum and the profile, sigma floored at 1e-6.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="116" x2="214" y2="116"/>
      <path class="skl-draw c-mid" d="M24 114 q40 -74 80 0 q40 -54 86 0 L214 114" style="fill:none"/>
      <path class="skl-draw c-cal" d="M24 114 q40 -54 80 0 q40 -40 86 0 L214 114" style="fill:none"/>
      <line class="skl-draw c-fin" x1="64" y1="74" x2="64" y2="92" style="stroke-width:1.6"/>
      <line class="skl-draw c-fin" x1="150" y1="82" x2="150" y2="98" style="stroke-width:1.6"/>
      <text x="120" y="22" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">L = mean(residual^2)</text>`; },
    anim: null,
  },

  adam: {
    tip: "Adam (eta = 0.2) runs as one lax.scan of T = 3000 steps, clamping each width to [sigma_lo, sigma_hi].",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="120" x2="214" y2="120"/>
      <line class="skl-axis" x1="28" y1="22" x2="28" y2="120"/>
      <line class="skl-dash c-faint" x1="28" y1="40" x2="214" y2="40"/>
      <line class="skl-dash c-faint" x1="28" y1="104" x2="214" y2="104"/>
      <path class="skl-draw c-cal" d="M28 100 C70 96 84 70 108 56 S170 44 214 44" style="fill:none"/>
      <circle class="sk-live skl-pop f-cal" cx="214" cy="44" r="4"/>`; },
    anim: FlowSketches.pulse,
  },

  scoreK: {
    tip: "Each order K scores as MSE_K + lambda_K x K, a flat per-slot charge, so a Gaussian is kept only when it earns it.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="32" y1="118" x2="214" y2="118"/>
      <rect x="44" y="58" width="20" height="60" class="skl-pop f-mid"/>
      <rect x="44" y="52" width="20" height="6" class="skl-pop f-fin"/>
      <rect x="92" y="92" width="20" height="26" class="skl-pop f-mid"/>
      <rect x="92" y="80" width="20" height="12" class="skl-pop f-fin"/>
      <rect x="140" y="86" width="20" height="32" class="skl-pop f-mid"/>
      <rect x="140" y="62" width="20" height="24" class="skl-pop f-fin"/>
      <rect x="188" y="80" width="20" height="38" class="skl-pop f-mid"/>
      <rect x="188" y="44" width="20" height="36" class="skl-pop f-fin"/>
      <text x="54" y="130" style="fill:#4a5a6b;font-size:7px">1</text>
      <text x="146" y="130" style="fill:#4a5a6b;font-size:7px">3</text>`; },
    anim: null,
  },

  selectK: {
    tip: "The penalised score is minimised over K, ties broken toward the smaller K.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="32" y1="116" x2="214" y2="116"/>
      <rect x="44" y="48" width="22" height="68" class="skl-pop f-mid"/>
      <rect class="sk-live skl-pop f-cal" x="92" y="84" width="22" height="32"/>
      <rect x="140" y="76" width="22" height="40" class="skl-pop f-mid"/>
      <rect x="188" y="62" width="22" height="54" class="skl-pop f-mid"/>
      <path class="skl-draw c-cal" d="M103 36 L103 62 M97 56 L103 62 L109 56" style="fill:none"/>
      <text x="103" y="30" text-anchor="middle" style="fill:#4fd6c4;font-size:9px;font-weight:600">K*=2</text>`; },
    anim: FlowSketches.pulse,
  },

  rescale: {
    tip: "The winner's amplitudes scale back by s to raw units; means and widths pass through unchanged.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="118" x2="214" y2="118"/>
      <line class="skl-dash c-faint" x1="24" y1="56" x2="214" y2="56"/>
      <text x="28" y="52" style="fill:#7e8aa0;font-size:7px">1.0 (norm)</text>
      <path class="skl-draw c-faint" d="M40 116 q40 -56 80 0 q34 -40 70 0" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-fin" d="M40 116 q40 -84 80 0 q34 -60 70 0" style="fill:none"/>
      <text x="150" y="40" style="fill:#c4a3ff;font-size:8px">x s</text>`; },
    anim: null,
  },

  assemble: {
    tip: "Active components sort by ascending mean, inactive slots drop to the end, into the interleaved 3K target.",
    build(svg) { svg.innerHTML = `
      <rect x="40" y="40" width="26" height="20" class="skl-pop f-cal"/>
      <rect x="40" y="66" width="26" height="20" class="skl-pop f-cal"/>
      <rect x="40" y="92" width="26" height="20" class="skl-pop f-faint"/>
      <text x="86" y="80" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect x="118" y="58" width="16" height="28" class="skl-pop f-fin"/>
      <rect x="136" y="58" width="16" height="28" class="skl-pop f-fin"/>
      <rect x="154" y="58" width="16" height="28" class="skl-pop f-fin"/>
      <rect x="172" y="58" width="16" height="28" class="skl-pop f-faint" style="opacity:.4"/>
      <rect x="190" y="58" width="16" height="28" class="skl-pop f-faint" style="opacity:.4"/>
      <text x="118" y="100" style="fill:#c4a3ff;font-size:7px">a mu sig a mu sig</text>`; },
    anim: null,
  },

  quality: {
    tip: "Per-pixel R-squared compares the reconstruction to the profile (1e-12 stabiliser), painting a fit-quality map.",
    build(svg) {
      const cells = [[0.95,"f-cal"],[0.9,"f-cal"],[0.6,"f-mid"],[0.7,"f-mid"],[0.92,"f-cal"],[0.88,"f-cal"],[0.85,"f-cal"],[0.4,"f-faint"],[0.9,"f-cal"]];
      let m = "";
      cells.forEach((cl, i) => { const x = 132 + (i % 3) * 26, y = 36 + Math.floor(i / 3) * 26; m += `<rect class="sk-live skl-pop ${cl[1]}" x="${x}" y="${y}" width="22" height="22" rx="2" style="opacity:${cl[0]}"/>`; });
      svg.innerHTML = `
        <line class="skl-axis" x1="24" y1="116" x2="108" y2="116"/>
        <path class="skl-draw c-meas" d="M24 114 L48 60 L72 96 L96 110" style="fill:none;opacity:.5"/>
        <path class="skl-draw c-cal" d="M24 114 q24 -58 44 -54 q22 4 22 40 q8 14 18 14" style="fill:none"/>
        <text x="40" y="34" style="fill:#4fd6c4;font-size:9px">R2</text>
        ${m}`;
    },
    anim: FlowSketches.pulse,
  },

  diagnostics: {
    tip: "Post-hoc: the runner-up margin over L_K* flags ambiguous pixels (< 0.05); contrast uses the lowest-amplitude quartile as floor.",
    build(svg) { svg.innerHTML = `
      <text x="34" y="30" style="fill:#c4a3ff;font-size:8px">m_rel</text>
      <rect x="34" y="36" width="92" height="12" rx="2" class="skl-pop f-faint" style="opacity:.3"/>
      <rect x="34" y="36" width="52" height="12" rx="2" class="skl-pop f-fin"/>
      <line class="skl-axis" x1="132" y1="120" x2="214" y2="120"/>
      <line class="skl-dash c-faint" x1="132" y1="96" x2="214" y2="96"/>
      <text x="214" y="92" text-anchor="end" style="fill:#7e8aa0;font-size:7px">floor (Q1)</text>
      <path class="skl-draw c-cal" d="M134 120 C152 50, 180 50, 198 120" style="fill:rgba(79,214,196,0.10)"/>
      <line class="skl-dash c-cal" x1="166" y1="96" x2="166" y2="62" style="stroke-width:1.4"/>
      <text x="171" y="82" style="fill:#4fd6c4;font-size:7px">C_dB</text>`; },
    anim: null,
  },

  splitgeom: {
    tip: "Azimuth splits 70/15/15 into contiguous, non-overlapping train, val and test bands.",
    build(svg) { svg.innerHTML = `
      <rect x="40" y="22" width="160" height="74" class="skl-pop f-mid" style="opacity:.85"/>
      <rect x="40" y="96" width="160" height="16" class="skl-pop f-cal" style="opacity:.85"/>
      <rect x="40" y="112" width="160" height="16" class="skl-pop f-fin" style="opacity:.85"/>
      <text x="120" y="62" text-anchor="middle" style="fill:#0b1014;font-size:9px">train 70%</text>
      <text x="120" y="107" text-anchor="middle" style="fill:#0b1014;font-size:7px">val 15%</text>
      <text x="120" y="123" text-anchor="middle" style="fill:#0b1014;font-size:7px">test 15%</text>`; },
    anim: null,
  },

  localslice: {
    tip: "Subtracting the crop origin az0 turns absolute azimuth bounds into zero-based slices.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="50" x2="214" y2="50"/>
      <text x="30" y="40" style="fill:#7e8aa0;font-size:7px">absolute</text>
      <rect x="92" y="42" width="78" height="16" class="skl-pop f-mid"/>
      <line class="skl-axis" x1="30" y1="104" x2="214" y2="104"/>
      <text x="30" y="124" style="fill:#7e8aa0;font-size:7px">local (0-based)</text>
      <rect x="30" y="96" width="78" height="16" class="skl-pop f-cal"/>
      <path class="skl-draw c-cal" d="M131 60 L60 94 M66 90 L60 94 L66 98" style="fill:none"/>
      <text x="138" y="80" style="fill:#4fd6c4;font-size:8px">- az0</text>`; },
    anim: null,
  },

  secselect: {
    tip: "Qualified labels in L_req map to positional indices, gathered alike from the secondaries and interferograms.",
    build(svg) {
      let row = "";
      for (let i = 0; i < 7; i++) { const sel = (i === 3 || i === 5 || i === 6); row += `<rect class="skl-pop ${sel ? "f-cal" : "f-faint"}" x="${28 + i * 24}" y="32" width="20" height="20" style="opacity:${sel ? 1 : 0.5}"/>`; if (sel) row += `<rect class="sk-live" x="${28 + i * 24}" y="32" width="20" height="20" style="fill:none;stroke:#4fd6c4;stroke-width:2.5"/>`; }
      svg.innerHTML = `
        ${row}
        <text x="120" y="80" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">pi = {3, 5, 6}</text>
        <rect x="100" y="96" width="20" height="20" class="skl-pop f-cal"/>
        <rect x="124" y="96" width="20" height="20" class="skl-pop f-cal"/>
        <rect x="148" y="96" width="20" height="20" class="skl-pop f-cal"/>`;
    },
    anim: FlowSketches.pulse,
  },

  stack: {
    tip: "Primary at slot 0, Ns secondaries in X[1:1+Ns], Ni interferograms after, into one complex buffer.",
    build(svg) { svg.innerHTML = `
      <rect x="38" y="30" width="44" height="18" class="skl-pop f-meas"/>
      <text x="60" y="43" text-anchor="middle" style="fill:#0b1014;font-size:8px">s0</text>
      <rect x="38" y="52" width="44" height="18" class="skl-pop f-mid"/>
      <rect x="38" y="74" width="44" height="18" class="skl-pop f-mid"/>
      <rect x="38" y="96" width="44" height="18" class="skl-pop f-cal"/>
      <rect x="38" y="118" width="44" height="18" class="skl-pop f-cal"/>
      <text x="100" y="86" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect x="134" y="30" width="72" height="106" rx="3" class="skl-draw c-fin" style="fill:rgba(196,163,255,0.08)"/>
      <text x="170" y="92" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">X buffer</text>`; },
    anim: null,
  },

  patchgrid: {
    tip: "A strided PxP window tiles the region; the row/col counts let the last patch cover the far border.",
    build(svg) {
      let g = "";
      for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) g += `<rect x="${40 + c * 41}" y="${30 + r * 32}" width="40" height="30" class="skl-pop f-mid" style="opacity:.16;stroke:#f5b971;stroke-width:.8"/>`;
      svg.innerHTML = `${g}<rect class="sk-live" x="81" y="62" width="40" height="30" style="fill:none;stroke:#4fd6c4;stroke-width:2.2"/>`;
    },
    anim: FlowSketches.pulse,
  },

  padgeom: {
    tip: "The azimuth deficit pv splits floor(pv/2) on top, the rest below; odd deficits go to the bottom.",
    build(svg) { svg.innerHTML = `
      <rect x="78" y="44" width="84" height="62" class="skl-pop f-mid" style="opacity:.8"/>
      <text x="120" y="80" text-anchor="middle" style="fill:#0b1014;font-size:8px">region</text>
      <rect x="78" y="28" width="84" height="14" class="skl-pop f-cal" style="opacity:.5"/>
      <text x="170" y="38" style="fill:#4fd6c4;font-size:7px">floor(pv/2)</text>
      <rect x="78" y="106" width="84" height="18" class="skl-pop f-cal" style="opacity:.5"/>
      <text x="170" y="120" style="fill:#4fd6c4;font-size:7px">pv-floor(pv/2)</text>`; },
    anim: null,
  },

  extract: {
    tip: "The read window is deep-copied (never aliases the mmap), then reflect-padded by the shared routine.",
    build(svg) { svg.innerHTML = `
      <rect x="28" y="32" width="74" height="74" class="skl-draw c-faint" style="fill:none"/>
      <rect x="58" y="62" width="44" height="44" class="skl-pop f-meas" style="opacity:.75"/>
      <text x="110" y="78" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect x="138" y="42" width="64" height="64" class="skl-pop f-cal" style="opacity:.3"/>
      <rect x="148" y="52" width="44" height="44" class="skl-pop f-mid"/>
      <text x="170" y="124" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">pad(copy)</text>`; },
    anim: null,
  },

  represent: {
    tip: "An SLC pass keeps |p|, an interferogram keeps its phase; normalised re/im divide by m=|p| (1 if |p|=0).",
    build(svg) { svg.innerHTML = `
      <circle cx="64" cy="70" r="32" class="skl-axis" style="fill:none;opacity:.5"/>
      <line class="skl-axis" x1="26" y1="70" x2="102" y2="70"/>
      <line class="skl-axis" x1="64" y1="34" x2="64" y2="106"/>
      <line class="skl-draw c-meas" x1="64" y1="70" x2="90" y2="52"/>
      <circle cx="90" cy="52" r="3.2" class="skl-pop f-meas"/>
      <path class="skl-dash c-mid" d="M82 70 A18 18 0 0 0 77 56" style="fill:none"/>
      <text x="64" y="118" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">complex p</text>
      <text x="120" y="74" style="fill:#7e8aa0;font-size:13px">&#8594;</text>
      <rect x="146" y="42" width="44" height="15" rx="2" class="skl-pop f-cal"/>
      <text x="196" y="53" style="fill:#4fd6c4;font-size:7px">|p|</text>
      <rect x="146" y="64" width="30" height="15" rx="2" class="skl-pop f-mid"/>
      <text x="182" y="75" style="fill:#f5b971;font-size:7px">ang</text>`; },
    anim: null,
  },

  assemble_in: {
    tip: "Real channels concatenate in fixed order: primary, secondaries, interferograms, optional DEM last.",
    build(svg) { svg.innerHTML = `
      <rect x="28" y="44" width="22" height="40" class="skl-pop f-meas"/>
      <rect x="54" y="44" width="22" height="40" class="skl-pop f-mid"/>
      <rect x="80" y="44" width="22" height="40" class="skl-pop f-mid"/>
      <rect x="106" y="44" width="22" height="40" class="skl-pop f-cal"/>
      <rect x="132" y="44" width="22" height="40" class="skl-pop f-faint"/>
      <text x="91" y="100" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">r0 | rS | rI | D</text>
      <rect x="40" y="110" width="130" height="22" rx="2" class="skl-draw c-cal" style="fill:rgba(79,214,196,0.12)"/>
      <text x="105" y="125" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">x : C_in</text>`; },
    anim: null,
  },

  target: {
    tip: "Channels are gathered from the interleaved (a, mu, sigma) GT; all three roles keep every n_g*3 channel.",
    build(svg) {
      const cls = ["f-meas", "f-mid", "f-cal"], roles = ["a", "mu", "s"];
      let row = "", out = "";
      for (let i = 0; i < 9; i++) { const x = 30 + i * 20, r = i % 3; row += `<rect class="skl-pop ${cls[r]}" x="${x}" y="40" width="16" height="22"/><text x="${x + 8}" y="55" text-anchor="middle" style="fill:#0b1014;font-size:7px">${roles[r]}</text>`; out += `<rect class="sk-live skl-pop f-cal" x="${x}" y="92" width="16" height="22"/>`; }
      svg.innerHTML = `<text x="120" y="30" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">interleaved theta</text>${row}<text x="120" y="80" text-anchor="middle" style="fill:#7e8aa0;font-size:12px">&#8595;</text>${out}`;
    },
    anim: FlowSketches.pulse,
  },

  augment_geo: {
    tip: "On train only, the sampled flip/rot90 is applied alike to x and y, keeping every pixel aligned.",
    build(svg) { svg.innerHTML = `
      <rect x="42" y="36" width="52" height="52" class="skl-draw c-meas" style="fill:none"/>
      <polygon points="50,80 50,44 74,44" style="fill:#6ea8ff;opacity:.7"/>
      <text x="68" y="100" text-anchor="middle" style="fill:#6ea8ff;font-size:8px">x</text>
      <text x="120" y="66" text-anchor="middle" style="fill:#f5b971;font-size:8px">flip</text>
      <rect x="146" y="36" width="52" height="52" class="skl-draw c-cal" style="fill:none"/>
      <polygon points="190,80 190,44 166,44" style="fill:#4fd6c4;opacity:.7"/>
      <text x="172" y="100" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">y</text>`; },
    anim: null,
  },

  slotkeys: {
    tip: "The strided layout labels each channel by family/slot, so pass/mag, ifg/phase and dem/elev get their own norm.",
    build(svg) {
      const L = [["pass/mag", "f-meas", "#6ea8ff"], ["pass/mag", "f-meas", "#6ea8ff"], ["ifg/phase", "f-mid", "#f5b971"], ["ifg/phase", "f-mid", "#f5b971"], ["dem/elev", "f-faint", "#7e8aa0"]];
      let s = "";
      L.forEach((l, i) => { const x = 34 + i * 36; s += `<rect class="skl-pop ${l[1]}" x="${x}" y="34" width="28" height="28"/><line x1="${x + 14}" y1="64" x2="${x + 14}" y2="92" style="stroke:${l[2]};stroke-width:1.3"/><text x="${x + 14}" y="106" text-anchor="middle" transform="rotate(38 ${x + 14} 106)" style="fill:${l[2]};font-size:6px">${l[0]}</text>`; });
      svg.innerHTML = s;
    },
    anim: null,
  },

  fitstats: {
    tip: "On train only (float64): magnitudes use robust-IQR-log1p, others z-score, ifg phase fixed pi; scale floored at 1e-8.",
    build(svg) {
      const hs = [14, 26, 40, 52, 46, 32, 20, 10];
      let b = "";
      hs.forEach((h, i) => { const x = 60 + i * 14; b += `<rect class="skl-pop f-meas" x="${x}" y="${112 - h}" width="12" height="${h}" style="opacity:.8"/>`; });
      svg.innerHTML = `<line class="skl-axis" x1="40" y1="112" x2="200" y2="112"/>${b}<line class="skl-dash c-cal" x1="116" y1="40" x2="116" y2="112"/><text x="116" y="34" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">mu_c</text>`;
    },
    anim: null,
  },

  normalise: {
    tip: "Subtracting mu_c and dividing by s_c gives each slot zero mean and unit scale across every split.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="104" x2="214" y2="104"/>
      <line class="skl-dash c-faint" x1="120" y1="34" x2="120" y2="110"/>
      <text x="120" y="122" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">0</text>
      <path class="skl-draw c-faint" d="M156 104 C166 60 198 60 208 104" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-cal" d="M92 104 C106 48 134 48 148 104" style="fill:none"/>
      <path class="skl-draw c-mid" d="M168 104 L150 104 M156 100 L150 104 L156 108" style="fill:none"/>`; },
    anim: null,
  },

  noise: {
    tip: "On train only, with probability p_N, std-0.01 Gaussian noise jitters x-hat; the target stays untouched.",
    build(svg) { svg.innerHTML = `
      <path class="skl-draw c-faint" d="M30 80 Q70 42 110 80 T190 80" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-fin" d="M30 82 Q50 60 70 64 Q90 36 110 78 Q130 92 150 70 Q170 50 190 76" style="fill:none"/>
      <text x="120" y="116" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">x-hat + N(0, 0.01^2)</text>`; },
    anim: null,
  },

  denorm: {
    tip: "The inverse scales by s_c, adds mu_c, and for log1p slots clips to [0, log1p(1000)] before expm1.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="104" x2="214" y2="104"/>
      <line class="skl-dash c-mid" x1="30" y1="48" x2="214" y2="48"/>
      <text x="208" y="44" text-anchor="end" style="fill:#f5b971;font-size:7px">log1p(1000)</text>
      <path class="skl-draw c-cal" d="M40 104 C72 50 150 48 200 48" style="fill:none"/>
      <text x="120" y="124" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">expm1(clip(x s + mu))</text>`; },
    anim: null,
  },

  forward: {
    tip: "One forward pass maps the input patch to 3K interleaved (a, mu, sigma) channels per pixel.",
    build(svg) { svg.innerHTML = `
      <rect x="24" y="56" width="20" height="40" rx="2" class="skl-pop f-meas"/>
      <path class="skl-draw c-faint" d="M56 48 L100 64 L100 96 L56 112 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M108 64 L140 74 L140 94 L108 104 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M148 74 L168 82 L168 100 L148 108 Z" style="fill:none"/>
      <rect x="178" y="46" width="34" height="9" rx="2" class="skl-pop f-cal"/>
      <rect x="178" y="58" width="34" height="9" rx="2" class="skl-pop f-cal" style="opacity:.7"/>
      <rect x="178" y="70" width="34" height="9" rx="2" class="skl-pop f-cal" style="opacity:.5"/>
      <text x="195" y="96" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">a mu s</text>`; },
    anim: null,
  },

  tdenorm: {
    tip: "expm1 inverts the log1p amplitude and sigma channels; the pre-exponent value is clamped so the physical output stays within [0, 1000].",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="214" y2="118"/>
      <line class="skl-axis" x1="30" y1="22" x2="30" y2="118"/>
      <line class="skl-dash c-mid" x1="30" y1="40" x2="214" y2="40"/>
      <text x="206" y="36" text-anchor="end" style="fill:#f5b971;font-size:7px">clamp</text>
      <path class="skl-draw c-cal" d="M30 116 Q120 114 166 40 L214 40" style="fill:none"/>`; },
    anim: null,
  },

  clamp: {
    tip: "Out-of-bounds a, mu and sigma clip to grid limits but keep a 0.1 leaky slope so gradients still flow.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="214" y2="118"/>
      <line class="skl-dash c-faint" x1="62" y1="20" x2="62" y2="120"/>
      <line class="skl-dash c-faint" x1="182" y1="20" x2="182" y2="120"/>
      <path class="skl-dash c-faint" d="M30 124 L214 18" style="opacity:.3"/>
      <path class="skl-draw c-cal" d="M30 108 L62 96 L182 34 L214 32" style="fill:none"/>
      <text x="48" y="132" style="fill:#7e8aa0;font-size:7px">min</text>
      <text x="170" y="132" style="fill:#7e8aa0;font-size:7px">max</text>`; },
    anim: null,
  },

  renorm: {
    tip: "(log1p - offset) / scale maps the clamped physical predictions back into label-normalised units.",
    build(svg) { svg.innerHTML = `
      <rect x="26" y="50" width="44" height="50" rx="3" class="skl-pop f-cal"/>
      <text x="48" y="79" text-anchor="middle" style="fill:#0b1014;font-size:9px">12.4</text>
      <text x="48" y="116" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">phys</text>
      <path class="skl-draw c-mid" d="M76 75 L162 75 M154 69 L162 75 L154 81" style="fill:none"/>
      <text x="119" y="68" text-anchor="middle" style="fill:#f5b971;font-size:7px">(log1p-l)/s</text>
      <rect x="170" y="50" width="44" height="50" rx="3" class="skl-pop f-meas"/>
      <text x="192" y="79" text-anchor="middle" style="fill:#0b1014;font-size:9px">0.74</text>
      <text x="192" y="116" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">norm</text>`; },
    anim: null,
  },

  reconstruct: {
    tip: "Predicted and GT parameters each sum K Gaussians into an elevation curve; the GT curve is built once under no_grad.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="216" y2="118"/>
      <path class="skl-draw c-faint" d="M40 118 Q70 70 100 118" style="fill:none;opacity:.4"/>
      <path class="skl-draw c-faint" d="M96 118 Q128 48 160 118" style="fill:none;opacity:.4"/>
      <path class="skl-draw c-faint" d="M150 118 Q176 82 202 118" style="fill:none;opacity:.4"/>
      <path class="skl-draw c-cal" d="M40 118 Q70 70 100 100 Q128 48 160 92 Q176 82 202 118" style="fill:none"/>
      <path class="skl-dash c-meas" d="M40 118 Q72 76 102 98 Q130 54 162 90 Q178 86 202 118" style="fill:none;opacity:.6"/>`; },
    anim: null,
  },

  residual: {
    tip: "The elementwise y-hat - y is the residual shared by the MSE, L1, Huber and Charbonnier terms.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="80" x2="216" y2="80"/>
      <path class="skl-draw c-cal" d="M30 70 Q60 30 90 56 Q120 18 150 50 Q180 44 214 70" style="fill:none"/>
      <path class="skl-dash c-meas" d="M30 74 Q60 40 90 60 Q120 30 150 56 Q180 52 214 74" style="fill:none"/>
      <line class="sk-live skl-pop" x1="60" y1="48" x2="60" y2="60" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <line class="sk-live skl-pop" x1="120" y1="22" x2="120" y2="32" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <line class="sk-live skl-pop" x1="150" y1="50" x2="150" y2="58" style="stroke:#f5b971;stroke-width:3;opacity:1"/>`; },
    anim: FlowSketches.pulse,
  },

  curvepoint: {
    tip: "Four pointwise residual reductions: MSE squares, L1 magnitude, Huber bends at delta, Charbonnier smooths with epsilon.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="120" y1="118" x2="120" y2="22"/>
      <line class="skl-axis" x1="28" y1="100" x2="214" y2="100"/>
      <path class="skl-draw c-cal" d="M40 30 Q120 134 200 30" style="fill:none"/>
      <path class="skl-dash c-mid" d="M40 38 L120 100 L200 38" style="fill:none"/>
      <path class="skl-draw c-faint" d="M40 40 Q86 54 100 86 L120 100 L140 86 Q154 54 200 40" style="fill:none"/>
      <text x="150" y="40" style="fill:#4fd6c4;font-size:7px">MSE</text>
      <text x="44" y="44" style="fill:#f5b971;font-size:7px">L1</text>`; },
    anim: null,
  },

  curveshape: {
    tip: "The default curve term: magnitude-free cosine angle between predicted and target profiles over valid pixels.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="102" y1="116" x2="102" y2="32"/>
      <line class="skl-axis" x1="80" y1="96" x2="176" y2="96"/>
      <line class="skl-draw c-cal" x1="102" y1="96" x2="164" y2="42"/>
      <line class="skl-draw c-meas" x1="102" y1="96" x2="148" y2="56"/>
      <path class="skl-dash c-faint" d="M132 70 A 34 34 0 0 1 138 78" style="fill:none"/>
      <text x="140" y="66" style="fill:#7e8aa0;font-size:7px">cos</text>`; },
    anim: null,
  },

  physgeom: {
    tip: "kz scales the perpendicular baseline by 4pi/(lambda r0 sin theta) to build the steering phasors.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="40" y1="120" x2="40" y2="28"/>
      <line class="skl-axis" x1="40" y1="120" x2="120" y2="120"/>
      <circle cx="40" cy="44" r="3" class="skl-pop f-faint"/>
      <line class="skl-dash c-mid" x1="40" y1="44" x2="116" y2="70"/>
      <circle cx="116" cy="70" r="3" class="skl-pop f-meas"/>
      <text x="62" y="50" style="fill:#f5b971;font-size:7px">b_perp</text>
      <text x="146" y="76" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <circle cx="190" cy="80" r="24" class="skl-axis" style="fill:none;opacity:.5"/>
      <line class="skl-draw c-cal" x1="190" y1="80" x2="207" y2="63"/>
      <circle cx="207" cy="63" r="3.2" class="skl-pop f-cal"/>
      <text x="158" y="124" style="fill:#4fd6c4;font-size:7px">exp(j kz xi)</text>`; },
    anim: null,
  },

  physmoments: {
    tip: "Ratio terms compare integrated power and the mass, centroid and spread moments over GT-strong pixels.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="216" y2="118"/>
      <path class="skl-draw c-cal" d="M40 118 Q90 40 124 70 Q150 92 200 118" style="fill:rgba(79,214,196,0.12)"/>
      <line class="skl-dash c-mid" x1="112" y1="118" x2="112" y2="50"/>
      <circle cx="112" cy="50" r="3.5" class="skl-pop f-mid"/>
      <text x="116" y="48" style="fill:#f5b971;font-size:7px">z-bar</text>
      <line class="skl-dash c-faint" x1="84" y1="100" x2="140" y2="100"/>
      <text x="92" y="114" style="fill:#7e8aa0;font-size:7px">sigma_z</text>`; },
    anim: null,
  },

  physcov: {
    tip: "Coherence compares the normalised characteristic functions; covariance matching transforms only R[P-T].",
    build(svg) {
      const m = FlowSketches.grid(3, (r, c) => { const x = 132 + c * 26, y = 36 + r * 26; const cl = r === c ? "sk-live skl-pop f-mid" : "skl-pop f-faint"; const op = r === c ? 1 : 0.3; return `<rect class="${cl}" x="${x}" y="${y}" width="22" height="22" rx="2" style="opacity:${op}"/>`; });
      svg.innerHTML = `
        <line class="skl-axis" x1="34" y1="104" x2="110" y2="104"/>
        <path class="skl-draw c-cal" d="M40 104 C56 56, 72 56, 90 104" style="fill:none"/>
        <path class="skl-dash c-mid" d="M46 104 C62 70, 80 70, 100 104" style="fill:none"/>
        <text x="38" y="44" style="fill:#7e8aa0;font-size:7px">gamma_P vs T</text>
        ${m}
        <text x="171" y="128" text-anchor="middle" style="fill:#f5b971;font-size:7px">R[P-T]</text>`;
    },
    anim: FlowSketches.pulse,
  },

  physcapon: {
    tip: "Capon synthesises R[P], adds adaptive diagonal loading, then solves the loaded system for a mass-normalised spectrum.",
    build(svg) { svg.innerHTML = `
      <rect x="36" y="40" width="48" height="48" rx="2" class="skl-pop f-mid" style="opacity:.5"/>
      <line class="skl-draw c-fin" x1="36" y1="40" x2="84" y2="88" style="stroke-width:3"/>
      <text x="40" y="104" style="fill:#7e8aa0;font-size:7px">R + eI</text>
      <path class="skl-draw c-mid" d="M92 64 L132 64 M124 59 L132 64 L124 69" style="fill:none"/>
      <line class="skl-axis" x1="150" y1="100" x2="214" y2="100"/>
      <path class="skl-draw c-cal" d="M152 100 Q178 40 184 78 Q192 52 212 100" style="fill:none"/>`; },
    anim: null,
  },

  paramterms: {
    tip: "GT sorts by mu and predictions are permuted onto it by optimal assignment (hungarian, the default); empty slots mask to zero weight. Param-L1 is active-normalised in normalised space, TV penalises roughness.",
    build(svg) { svg.innerHTML = `
      <rect x="34" y="42" width="22" height="20" rx="2" class="skl-pop f-cal"/>
      <rect x="34" y="66" width="22" height="20" rx="2" class="skl-pop f-cal"/>
      <rect x="34" y="90" width="22" height="20" rx="2" class="skl-dash c-faint" style="fill:none"/>
      <text x="45" y="124" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">mask</text>
      <text x="86" y="78" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect x="150" y="40" width="62" height="62" class="skl-axis" style="fill:none;opacity:.3"/>
      <path class="skl-draw c-cal" d="M158 92 L170 60 L182 80 L194 52 L206 72" style="fill:none"/>
      <text x="170" y="116" style="fill:#4fd6c4;font-size:7px">TV</text>`; },
    anim: null,
  },

  composite: {
    tip: "Each enabled term is scaled by its user weight; the weighted terms sum and divide by the total weight into one loss.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="140" y2="118"/>
      <rect x="36" y="92" width="14" height="26" class="skl-pop f-cal"/>
      <rect x="56" y="74" width="14" height="44" class="skl-pop f-cal"/>
      <rect x="76" y="100" width="14" height="18" class="skl-pop f-cal"/>
      <rect x="96" y="58" width="14" height="60" class="skl-pop f-cal"/>
      <rect x="116" y="86" width="14" height="32" class="skl-pop f-cal"/>
      <path class="skl-draw c-mid" d="M146 75 L176 75 M168 70 L176 75 L168 80" style="fill:none"/>
      <text x="160" y="68" text-anchor="middle" style="fill:#f5b971;font-size:7px">/ sum</text>
      <rect class="sk-live skl-pop f-fin" x="192" y="48" width="24" height="70"/>
      <text x="204" y="132" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">L</text>`; },
    anim: FlowSketches.pulse,
  },

  gradclip: {
    tip: "If the gradient norm exceeds tau, all gradients scale by tau/norm, landing exactly on the limit.",
    build(svg) { svg.innerHTML = `
      <circle cx="76" cy="80" r="44" class="skl-dash c-faint" style="fill:none;opacity:.5"/>
      <text x="40" y="36" style="fill:#7e8aa0;font-size:7px">tau</text>
      <line class="skl-dash c-faint" x1="76" y1="80" x2="124" y2="34" style="opacity:.5"/>
      <line class="skl-draw c-cal" x1="76" y1="80" x2="107" y2="50"/>
      <circle cx="76" cy="80" r="3" class="skl-pop f-faint"/>
      <circle cx="107" cy="50" r="3.5" class="skl-pop f-cal"/>
      <text x="130" y="80" style="fill:#4fd6c4;font-size:7px">g min(1, tau/|g|)</text>`; },
    anim: null,
  },

  adamw: {
    tip: "Adaptive moments with decoupled weight decay step the weights downhill, lowering the loss each epoch.",
    build(svg) { svg.innerHTML = `
      <path class="skl-draw c-faint" d="M30 36 Q120 156 210 36" style="fill:none;opacity:.5"/>
      <circle cx="42" cy="60" r="2.5" class="skl-pop f-mid" style="opacity:.4"/>
      <circle cx="70" cy="92" r="2.5" class="skl-pop f-mid" style="opacity:.4"/>
      <circle cx="98" cy="114" r="2.5" class="skl-pop f-mid" style="opacity:.4"/>
      <circle class="sk-live skl-pop f-fin" cx="120" cy="122" r="5"/>`; },
    anim: FlowSketches.pulse,
  },

  schedule: {
    tip: "Effective LR = base x cosine decay x linear warmup; the curriculum swaps objectives at swap epoch 15.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="216" y2="118"/>
      <line class="skl-axis" x1="28" y1="22" x2="28" y2="118"/>
      <path class="skl-draw c-mid" d="M28 110 L58 40" style="fill:none"/>
      <path class="skl-draw c-cal" d="M58 40 Q120 44 150 78 Q180 108 210 114" style="fill:none"/>
      <line class="skl-dash c-fin" x1="138" y1="22" x2="138" y2="118"/>
      <text x="142" y="32" style="fill:#c4a3ff;font-size:7px">swap</text>`; },
    anim: null,
  },

  checkpoint: {
    tip: "Validation checkpoints the best epoch; early stopping reverts to it after 15 evals without a new minimum.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="216" y2="118"/>
      <path class="skl-draw c-cal" d="M30 50 L62 72 L94 60 L120 90 L150 78 L180 96 L210 88" style="fill:none"/>
      <circle class="sk-live skl-pop f-fin" cx="120" cy="90" r="5"/>
      <text x="120" y="108" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">best</text>`; },
    anim: FlowSketches.pulse,
  },

  pae_stack: {
    tip: "The mmap parameter crop is de-interleaved by stride-3 into per-pixel amplitude, mean and width rows.",
    build(svg) {
      const cls = ["f-meas", "f-mid", "f-cal"];
      let top = "", rows = "";
      for (let i = 0; i < 9; i++) { const x = 30 + i * 20, r = i % 3; top += `<rect class="skl-pop ${cls[r]}" x="${x}" y="28" width="16" height="20"/>`; }
      for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) rows += `<rect class="skl-pop ${cls[r]}" x="${60 + c * 20}" y="${86 + r * 14}" width="16" height="12"/>`;
      svg.innerHTML = `<text x="120" y="22" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">interleaved theta</text>${top}<text x="120" y="72" text-anchor="middle" style="fill:#7e8aa0;font-size:12px">&#8595;</text>${rows}<text x="150" y="96" style="fill:#6ea8ff;font-size:7px">a</text><text x="150" y="110" style="fill:#f5b971;font-size:7px">mu</text><text x="150" y="124" style="fill:#4fd6c4;font-size:7px">sigma</text>`;
    },
    anim: null,
  },

  pae_select: {
    tip: "A pixel is active if any amplitude clears 1e-3; active pixels subsample, empties keep 5%, then shuffle.",
    build(svg) {
      const act = [1, 0, 1, 1, 0, 1, 1, 0, 1, 1];
      let cells = "", kept = "";
      for (let i = 0; i < 10; i++) { const x = 24 + i * 20, a = act[i]; cells += `<rect class="skl-pop ${a ? "f-cal" : "f-faint"}" x="${x}" y="34" width="16" height="16" style="opacity:${a ? 1 : 0.45}"/>`; }
      [0, 2, 5].forEach((i) => { kept += `<rect class="sk-live" x="${24 + i * 20}" y="34" width="16" height="16" style="fill:none;stroke:#4fd6c4;stroke-width:2.4"/>`; });
      svg.innerHTML = `${cells}${kept}<text x="120" y="76" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">a_max &gt; 1e-3</text><text x="120" y="106" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">kept + 5% empty, shuffled</text>`;
    },
    anim: FlowSketches.pulse,
  },

  pae_genesis: {
    tip: "Each kept pixel synthesises its profile by summing K Gaussians over the axis; this curve is input and target.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="216" y2="118"/>
      <path class="skl-draw c-faint" d="M40 118 Q66 66 92 118" style="fill:none;opacity:.45"/>
      <path class="skl-draw c-faint" d="M92 118 Q124 40 156 118" style="fill:none;opacity:.45"/>
      <path class="skl-draw c-faint" d="M150 118 Q178 84 206 118" style="fill:none;opacity:.45"/>
      <path class="skl-draw c-cal" d="M40 118 Q66 66 92 100 Q124 40 156 96 Q178 84 206 118" style="fill:none"/>
      <text x="120" y="134" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">sum_k a_k exp(...)</text>`; },
    anim: null,
  },

  pae_augment: {
    tip: "Train only: amplitude-scale, circular shift and flip (p=0.5) jitter the profile before normalisation.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="110" x2="216" y2="110"/>
      <path class="skl-draw c-faint" d="M40 110 Q80 46 120 110" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-cal" d="M124 110 Q164 46 204 110" style="fill:none"/>
      <path class="skl-draw c-mid" d="M96 60 L132 60 M124 55 L132 60 L124 65" style="fill:none"/>
      <text x="120" y="128" text-anchor="middle" style="fill:#f5b971;font-size:7px">scale / shift / flip</text>`; },
    anim: null,
  },

  pae_fitstats: {
    tip: "Train only, float64: loc and scale are the mean and std of log1p(c) over up to 100k profiles, scale floored 1e-6.",
    build(svg) {
      const hs = [10, 20, 34, 50, 58, 44, 28, 16, 8];
      let b = "";
      hs.forEach((h, i) => { const x = 52 + i * 15; b += `<rect class="skl-pop f-cal" x="${x}" y="${112 - h}" width="12" height="${h}" style="opacity:.8"/>`; });
      svg.innerHTML = `<line class="skl-axis" x1="40" y1="112" x2="204" y2="112"/>${b}<line class="skl-dash c-cal" x1="118" y1="36" x2="118" y2="112"/><text x="118" y="30" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">loc</text><text x="200" y="46" text-anchor="end" style="fill:#7e8aa0;font-size:7px">log1p(c)</text>`;
    },
    anim: null,
  },

  pae_normalise: {
    tip: "Standardise with (log1p(c') - loc)/scale, then on train add std-0.01 Gaussian noise in normalised units.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="104" x2="214" y2="104"/>
      <line class="skl-dash c-faint" x1="120" y1="34" x2="120" y2="110"/>
      <text x="120" y="122" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">0</text>
      <path class="skl-draw c-cal" d="M92 104 C106 48 134 48 148 104" style="fill:none"/>
      <line class="sk-live skl-pop" x1="108" y1="60" x2="108" y2="70" style="stroke:#c4a3ff;stroke-width:3"/>
      <line class="sk-live skl-pop" x1="120" y1="52" x2="120" y2="60" style="stroke:#c4a3ff;stroke-width:3"/>
      <line class="sk-live skl-pop" x1="132" y1="62" x2="132" y2="72" style="stroke:#c4a3ff;stroke-width:3"/>`; },
    anim: FlowSketches.pulse,
  },

  pae_encode: {
    tip: "The per-pixel profile is compressed by the encoder MLP to a d=24 bottleneck embedding.",
    build(svg) { svg.innerHTML = `
      <path class="skl-draw c-cal" d="M28 40 L28 112 L60 96 L60 56 Z" style="fill:rgba(79,214,196,0.10)"/>
      <path class="skl-draw c-faint" d="M72 52 L104 64 L104 90 L72 100 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M112 62 L140 72 L140 84 L112 92 Z" style="fill:none"/>
      <rect x="150" y="64" width="16" height="26" rx="2" class="sk-live skl-pop f-mid"/>
      <text x="158" y="108" text-anchor="middle" style="fill:#f5b971;font-size:7px">z : d=24</text>`; },
    anim: FlowSketches.pulse,
  },

  pae_embednorm: {
    tip: "The bottleneck is layernormed across its d channels (zero mean, unit variance); l2 or none are alternatives.",
    build(svg) {
      const hs = [18, -12, 26, -20, 10, -8, 22, -16];
      let b = "";
      hs.forEach((h, i) => { const x = 48 + i * 16, y = h >= 0 ? 76 - h : 76, ht = Math.abs(h); b += `<rect class="skl-pop f-mid" x="${x}" y="${y}" width="11" height="${ht}"/>`; });
      svg.innerHTML = `<line class="skl-axis" x1="40" y1="76" x2="200" y2="76"/>${b}<circle cx="120" cy="76" r="30" class="sk-live skl-dash c-cal" style="fill:none"/><text x="120" y="126" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">(z - mean)/std</text>`;
    },
    anim: FlowSketches.pulse,
  },

  pae_decode: {
    tip: "The decoder mirrors the encoder, projecting the normalised embedding back to a full-length profile.",
    build(svg) { svg.innerHTML = `
      <rect x="30" y="64" width="16" height="26" rx="2" class="skl-pop f-cal"/>
      <path class="skl-draw c-faint" d="M56 72 L84 62 L84 92 L56 82 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M92 64 L124 54 L124 100 L92 90 Z" style="fill:none"/>
      <path class="skl-draw c-cal" d="M132 44 L164 56 L164 98 L132 110 Z" style="fill:rgba(79,214,196,0.10)"/>
      <line class="skl-axis" x1="172" y1="110" x2="216" y2="110"/>
      <path class="skl-draw c-cal" d="M172 110 Q194 60 216 110" style="fill:none"/>`; },
    anim: null,
  },

  pae_recon: {
    tip: "The residual c-rec minus c-hat is reduced by MSE (default), L1, Huber (delta 1) or Charbonnier (eps 1e-3).",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="80" x2="216" y2="80"/>
      <path class="skl-draw c-cal" d="M30 70 Q64 26 96 54 Q128 16 160 50 Q186 44 214 70" style="fill:none"/>
      <path class="skl-dash c-faint" d="M30 74 Q64 40 96 60 Q128 32 160 56 Q186 52 214 74" style="fill:none"/>
      <line class="sk-live skl-pop" x1="64" y1="34" x2="64" y2="46" style="stroke:#f5b971;stroke-width:3"/>
      <line class="sk-live skl-pop" x1="128" y1="22" x2="128" y2="34" style="stroke:#f5b971;stroke-width:3"/>
      <line class="sk-live skl-pop" x1="160" y1="50" x2="160" y2="58" style="stroke:#f5b971;stroke-width:3"/>`; },
    anim: FlowSketches.pulse,
  },

  pae_paramgroups: {
    tip: "AdamW holds two groups, encoder and decoder, each with its own lr (3e-4) and weight decay (1e-4).",
    build(svg) { svg.innerHTML = `
      <rect x="30" y="44" width="80" height="60" rx="4" class="skl-draw c-cal" style="fill:rgba(79,214,196,0.10)"/>
      <text x="70" y="70" text-anchor="middle" style="fill:#4fd6c4;font-size:9px">encoder</text>
      <text x="70" y="88" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">eta 3e-4, wd 1e-4</text>
      <rect x="130" y="44" width="80" height="60" rx="4" class="skl-draw c-mid" style="fill:rgba(245,185,113,0.10)"/>
      <text x="170" y="70" text-anchor="middle" style="fill:#f5b971;font-size:9px">decoder</text>
      <text x="170" y="88" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">eta 3e-4, wd 1e-4</text>`; },
    anim: null,
  },

  pae_schedule: {
    tip: "Effective LR = base x cosine-anneal to 1e-6 over T=100 x linear warmup from 0.1 over 200 steps.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="216" y2="118"/>
      <line class="skl-axis" x1="28" y1="22" x2="28" y2="118"/>
      <path class="skl-draw c-mid" d="M28 110 L60 44" style="fill:none"/>
      <path class="skl-draw c-cal" d="M60 44 Q120 50 156 84 Q186 110 212 116" style="fill:none"/>
      <text x="52" y="38" style="fill:#f5b971;font-size:7px">warmup</text>
      <text x="150" y="68" style="fill:#4fd6c4;font-size:7px">cosine</text>`; },
    anim: null,
  },

  pae_gradstep: {
    tip: "The global grad norm clips to 1.0, then AdamW steps the weights downhill, lowering the loss each epoch.",
    build(svg) { svg.innerHTML = `
      <path class="skl-draw c-faint" d="M30 34 Q120 152 210 34" style="fill:none;opacity:.5"/>
      <circle cx="48" cy="58" r="2.5" class="skl-pop f-mid" style="opacity:.4"/>
      <circle cx="76" cy="92" r="2.5" class="skl-pop f-mid" style="opacity:.5"/>
      <circle cx="100" cy="114" r="2.5" class="skl-pop f-mid" style="opacity:.6"/>
      <circle class="sk-live skl-pop f-fin" cx="120" cy="122" r="5"/>
      <text x="120" y="140" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">clip tau=1</text>`; },
    anim: FlowSketches.pulse,
  },

  pae_checkpoint: {
    tip: "Validation every few epochs checkpoints the best epoch; early stopping restores it after patience=15.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="216" y2="118"/>
      <path class="skl-draw c-cal" d="M30 52 L60 74 L92 62 L120 92 L150 80 L180 98 L210 90" style="fill:none"/>
      <circle class="sk-live skl-pop f-fin" cx="120" cy="92" r="5"/>
      <text x="120" y="110" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">best theta*</text>`; },
    anim: FlowSketches.pulse,
  },

  iae_encode: {
    tip: "Stem lifts the patch to base_channels, strided stages downsample and widen it, a 1x1 head gives the latent code.",
    build(svg) { svg.innerHTML = `
      <rect x="22" y="46" width="22" height="58" rx="2" class="skl-pop f-meas"/>
      <text x="33" y="118" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">x</text>
      <path class="skl-draw c-faint" d="M56 46 L104 62 L104 88 L56 104 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M112 62 L150 72 L150 82 L112 92 Z" style="fill:none"/>
      <rect x="162" y="60" width="18" height="34" rx="2" class="sk-live skl-pop f-mid"/>
      <text x="171" y="110" text-anchor="middle" style="fill:#f5b971;font-size:7px">z0 : C_e</text>`; },
    anim: FlowSketches.pulse,
  },

  iae_embednorm: {
    tip: "l2 mode rescales each pixel's channel vector to unit length (1e-6 floor); layernorm standardises it; none passes through.",
    build(svg) { svg.innerHTML = `
      <circle cx="120" cy="76" r="44" class="skl-axis" style="fill:none;opacity:.55"/>
      <line class="skl-axis" x1="70" y1="76" x2="170" y2="76"/>
      <line class="skl-axis" x1="120" y1="30" x2="120" y2="122"/>
      <line x1="120" y1="76" x2="160" y2="48" style="stroke:#4a5a6b;stroke-width:1.4"/>
      <circle cx="160" cy="48" r="3" class="skl-pop f-faint"/>
      <line class="sk-live skl-draw c-cal" x1="120" y1="76" x2="151" y2="54"/>
      <circle class="sk-live skl-pop f-cal" cx="151" cy="54" r="3.6"/>
      <text x="120" y="116" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">||z|| = 1</text>`; },
    anim: FlowSketches.pulse,
  },

  iae_decode: {
    tip: "A 1x1 layer restores the bottleneck width, upsampling stages double resolution and halve width, a 1x1 head returns the patch.",
    build(svg) { svg.innerHTML = `
      <rect x="24" y="60" width="18" height="34" rx="2" class="skl-pop f-cal"/>
      <text x="33" y="110" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">z</text>
      <path class="skl-draw c-faint" d="M54 72 L92 62 L92 92 L54 82 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M100 62 L148 46 L148 108 L100 92 Z" style="fill:none"/>
      <rect x="176" y="46" width="24" height="62" rx="2" class="skl-pop f-cal"/>
      <text x="188" y="122" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">x-hat</text>`; },
    anim: null,
  },

  iae_residual: {
    tip: "The residual is the reconstruction minus the input patch itself; the autoencoder is self-supervised, so the input is the target.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="84" x2="216" y2="84"/>
      <path class="skl-draw c-meas" d="M30 78 Q64 44 96 68 Q128 36 160 62 Q188 56 214 76" style="fill:none;opacity:.7"/>
      <path class="skl-draw c-cal" d="M30 72 Q64 34 96 60 Q128 26 160 54 Q188 48 214 70" style="fill:none"/>
      <line class="sk-live skl-pop" x1="64" y1="34" x2="64" y2="44" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <line class="sk-live skl-pop" x1="128" y1="26" x2="128" y2="36" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <line class="sk-live skl-pop" x1="160" y1="54" x2="160" y2="62" style="stroke:#f5b971;stroke-width:3;opacity:1"/>`; },
    anim: FlowSketches.pulse,
  },

  iae_reconterm: {
    tip: "One term reduces the residual: MSE squares it, L1 takes magnitude, Huber bends at delta = 1, Charbonnier smooths with eps = 1e-3.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="120" y1="118" x2="120" y2="22"/>
      <line class="skl-axis" x1="28" y1="100" x2="214" y2="100"/>
      <path class="skl-draw c-cal" d="M40 30 Q120 134 200 30" style="fill:none"/>
      <path class="skl-dash c-mid" d="M40 38 L120 100 L200 38" style="fill:none"/>
      <path class="skl-draw c-faint" d="M40 40 Q86 54 100 86 L120 100 L140 86 Q154 54 200 40" style="fill:none"/>
      <text x="150" y="40" style="fill:#4fd6c4;font-size:7px">MSE</text>
      <text x="44" y="44" style="fill:#f5b971;font-size:7px">L1</text>`; },
    anim: null,
  },

  iae_gradclip: {
    tip: "The global gradient is rescaled onto the circle of radius tau = 1 so its norm never exceeds the threshold; floor eps = 1e-6.",
    build(svg) { svg.innerHTML = `
      <circle cx="120" cy="78" r="40" class="skl-axis" style="fill:none;opacity:.55"/>
      <text x="120" y="30" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">tau = 1</text>
      <line class="skl-dash c-faint" x1="120" y1="78" x2="184" y2="42"/>
      <circle cx="184" cy="42" r="3" class="skl-pop f-faint"/>
      <line class="sk-live skl-draw c-mid" x1="120" y1="78" x2="151" y2="60"/>
      <circle class="sk-live skl-pop f-mid" cx="151" cy="60" r="3.6"/>
      <text x="120" y="122" text-anchor="middle" style="fill:#f5b971;font-size:7px">clip to ||g|| = tau</text>`; },
    anim: FlowSketches.pulse,
  },

  iae_adamw: {
    tip: "Two AdamW groups (encoder, decoder) at lr 3e-4 and wd 1e-4 drive the reconstruction loss down over the epoch loop.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="120" x2="214" y2="120"/>
      <line class="skl-axis" x1="28" y1="22" x2="28" y2="120"/>
      <path class="skl-draw c-cal" d="M30 40 C70 46 96 92 130 104 S190 112 214 113" style="fill:none"/>
      <circle class="sk-live skl-pop f-cal" cx="214" cy="113" r="4"/>
      <text x="120" y="36" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">L down</text>`; },
    anim: FlowSketches.pulse,
  },

  iae_schedule: {
    tip: "The LR ramps up over 200 warmup steps, then follows a cosine decay to eta_min = 1e-6 across T = 100 epochs.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="214" y2="118"/>
      <line class="skl-axis" x1="28" y1="22" x2="28" y2="118"/>
      <line class="skl-dash c-faint" x1="58" y1="30" x2="58" y2="118"/>
      <path class="skl-draw c-mid" d="M28 108 L58 40" style="fill:none"/>
      <path class="skl-draw c-cal" d="M58 40 C110 44 168 96 214 112" style="fill:none"/>
      <text x="52" y="28" text-anchor="middle" style="fill:#f5b971;font-size:7px">warmup</text>
      <text x="150" y="62" style="fill:#4fd6c4;font-size:7px">cosine</text>`; },
    anim: null,
  },

  iae_checkpoint: {
    tip: "Eval runs every 5 epochs; the strict-improvement minimum of the val reconstruction loss is checkpointed, patience 15 restores it.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="214" y2="118"/>
      <line class="skl-axis" x1="28" y1="22" x2="28" y2="118"/>
      <path class="skl-draw c-cal" d="M30 40 C70 72 96 96 118 96 C150 96 182 72 214 58" style="fill:none"/>
      <line class="skl-dash c-faint" x1="118" y1="96" x2="118" y2="118"/>
      <circle class="sk-live skl-pop f-fin" cx="118" cy="96" r="4.5"/>
      <text x="118" y="34" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">best</text>`; },
    anim: FlowSketches.pulse,
  },

  jep_couple: {
    tip: "A pretrained profile autoencoder is frozen (or fine-tuned) and coupled to the backbone that predicts its embeddings.",
    build(svg) { svg.innerHTML = `
      <rect x="26" y="42" width="34" height="26" rx="3" class="skl-pop f-faint"/>
      <rect x="26" y="72" width="34" height="26" rx="3" class="skl-pop f-faint"/>
      <text x="43" y="59" text-anchor="middle" style="fill:#0b1014;font-size:7px">Enc</text>
      <text x="43" y="89" text-anchor="middle" style="fill:#0b1014;font-size:7px">Dec</text>
      <text x="43" y="114" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">AE frozen</text>
      <path class="skl-dash c-faint" d="M62 70 C88 70 92 70 112 70" style="fill:none"/>
      <rect x="116" y="48" width="46" height="46" rx="4" class="skl-draw c-cal" style="fill:rgba(79,214,196,0.12)"/>
      <text x="139" y="74" text-anchor="middle" style="fill:#4fd6c4;font-size:9px">f&#952;</text>
      <path class="skl-draw c-cal" d="M164 71 L188 71 M181 66 L188 71 L181 76" style="fill:none"/>
      <rect x="192" y="56" width="14" height="30" rx="2" class="skl-pop f-cal"/>
      <text x="199" y="100" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">z</text>`; },
    anim: null,
  },

  jep_predict: {
    tip: "One forward pass maps the input patch to a per-pixel latent embedding of width E.",
    build(svg) { svg.innerHTML = `
      <rect x="24" y="52" width="20" height="46" rx="2" class="skl-pop f-meas"/>
      <text x="34" y="112" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">x</text>
      <path class="skl-draw c-faint" d="M58 46 L104 62 L104 100 L58 116 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M112 60 L150 72 L150 96 L112 108 Z" style="fill:none"/>
      <rect x="182" y="44" width="26" height="9" rx="2" class="skl-pop f-cal"/>
      <rect x="182" y="56" width="26" height="9" rx="2" class="skl-pop f-cal" style="opacity:.8"/>
      <rect x="182" y="68" width="26" height="9" rx="2" class="skl-pop f-cal" style="opacity:.6"/>
      <rect x="182" y="80" width="26" height="9" rx="2" class="skl-pop f-cal" style="opacity:.45"/>
      <text x="195" y="104" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">z : E</text>`; },
    anim: null,
  },

  jep_gtcurve: {
    tip: "GT parameters are denormalised, rendered as a Gaussian-mixture curve, then log1p-standardised into the AE space.",
    build(svg) { svg.innerHTML = `
      <rect x="24" y="54" width="16" height="18" class="skl-pop f-faint"/>
      <rect x="24" y="74" width="16" height="18" class="skl-pop f-faint"/>
      <rect x="24" y="94" width="16" height="18" class="skl-pop f-faint"/>
      <text x="32" y="67" text-anchor="middle" style="fill:#0b1014;font-size:7px">a</text>
      <text x="32" y="87" text-anchor="middle" style="fill:#0b1014;font-size:7px">&#956;</text>
      <text x="32" y="107" text-anchor="middle" style="fill:#0b1014;font-size:7px">&#963;</text>
      <text x="54" y="88" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <line class="skl-axis" x1="80" y1="118" x2="214" y2="118"/>
      <path class="skl-draw c-cal" d="M80 114 L120 110 L146 58 L172 110 L214 116" style="fill:none"/>
      <path class="skl-dash c-mid" d="M80 116 L120 112 L146 80 L172 112 L214 116" style="fill:none;opacity:.7"/>
      <text x="150" y="52" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">&#947;</text>`; },
    anim: null,
  },

  jep_target: {
    tip: "The profile encoder embeds the GT curve into the target vector; by default its gradient is stopped (stopgrad).",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="104" x2="78" y2="104"/>
      <path class="skl-draw c-faint" d="M24 100 L40 100 L51 62 L62 100 L78 102" style="fill:none"/>
      <text x="50" y="120" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">&#947;n</text>
      <rect x="92" y="54" width="40" height="44" rx="4" class="skl-draw c-mid" style="fill:rgba(245,185,113,0.10)"/>
      <text x="112" y="80" text-anchor="middle" style="fill:#f5b971;font-size:8px">E&#966;</text>
      <line class="skl-dash c-faint" x1="150" y1="40" x2="150" y2="112"/>
      <text x="150" y="34" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">sg</text>
      <rect x="168" y="56" width="14" height="40" rx="2" class="skl-pop f-cal"/>
      <text x="175" y="110" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">z*</text>`; },
    anim: null,
  },

  jep_embednorm: {
    tip: "Both embeddings pass through the AE's embedding normalisation (layernorm by default) before they are compared.",
    build(svg) { svg.innerHTML = `
      <circle cx="120" cy="80" r="46" class="skl-dash c-faint" style="fill:none;opacity:.6"/>
      <line class="skl-axis" x1="120" y1="80" x2="120" y2="34" style="opacity:.4"/>
      <line class="skl-draw c-cal" x1="120" y1="80" x2="152" y2="46"/>
      <circle cx="152" cy="46" r="3.2" class="skl-pop f-cal"/>
      <text x="156" y="46" style="fill:#4fd6c4;font-size:8px">z_n</text>
      <line class="skl-draw c-mid" x1="120" y1="80" x2="90" y2="42"/>
      <circle cx="90" cy="42" r="3.2" class="skl-pop f-mid"/>
      <text x="60" y="42" style="fill:#f5b971;font-size:8px">z*_n</text>
      <text x="120" y="140" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">EN(z) : layernorm</text>`; },
    anim: null,
  },

  jep_embloss: {
    tip: "The match loss is the squared distance between the normalised prediction and target embeddings.",
    build(svg) { svg.innerHTML = `
      <rect x="40" y="34" width="160" height="86" rx="4" class="skl-axis" style="fill:none;opacity:.3"/>
      <circle cx="84" cy="94" r="5" class="skl-pop f-cal"/>
      <text x="84" y="112" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">z_n</text>
      <circle class="sk-live skl-pop f-mid" cx="150" cy="58" r="5"/>
      <text x="158" y="56" style="fill:#f5b971;font-size:7px">z*_n</text>
      <line class="sk-live skl-draw c-fin" x1="84" y1="94" x2="150" y2="58"/>
      <text x="104" y="84" style="fill:#c4a3ff;font-size:7px">|z_n - z*_n|&#178;</text>`; },
    anim: FlowSketches.pulse,
  },

  jep_recon: {
    tip: "The prediction is decoded back to a curve and compared to the GT curve, anchoring the embedding to real shape.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="116" x2="214" y2="116"/>
      <line class="skl-axis" x1="28" y1="40" x2="28" y2="116"/>
      <path class="skl-draw c-faint" d="M28 112 L74 108 L120 52 L166 108 L214 114" style="fill:none;opacity:.6"/>
      <text x="150" y="48" style="fill:#7e8aa0;font-size:7px">&#947;n</text>
      <path class="skl-draw c-cal" d="M28 114 L74 110 L120 66 L166 106 L214 114" style="fill:none"/>
      <text x="58" y="72" style="fill:#4fd6c4;font-size:7px">D&#966;(z_n)</text>`; },
    anim: null,
  },

  jep_total: {
    tip: "The total loss is the plain sum of the embedding-match term and the curve-reconstruction anchor.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="150" y2="118"/>
      <rect x="46" y="66" width="22" height="52" class="skl-pop f-cal"/>
      <text x="57" y="132" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">emb</text>
      <text x="80" y="98" text-anchor="middle" style="fill:#7e8aa0;font-size:12px">+</text>
      <rect x="98" y="88" width="22" height="30" class="skl-pop f-cal"/>
      <text x="109" y="132" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">rec</text>
      <path class="skl-draw c-mid" d="M156 84 L182 84 M175 79 L182 84 L175 89" style="fill:none"/>
      <rect class="sk-live skl-pop f-fin" x="190" y="52" width="24" height="66"/>
      <text x="202" y="132" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">L</text>`; },
    anim: FlowSketches.pulse,
  },

  jep_step: {
    tip: "AdamW steps the backbone and any fine-tuned AE group downhill, with warmup, cosine LR and gradient clipping.",
    build(svg) { svg.innerHTML = `
      <path class="skl-draw c-faint" d="M30 34 Q120 152 210 34" style="fill:none;opacity:.5"/>
      <circle cx="46" cy="58" r="2.5" class="skl-pop f-mid" style="opacity:.4"/>
      <circle cx="74" cy="92" r="2.5" class="skl-pop f-mid" style="opacity:.5"/>
      <circle cx="100" cy="114" r="2.5" class="skl-pop f-mid" style="opacity:.6"/>
      <circle class="sk-live skl-pop f-fin" cx="120" cy="124" r="5"/>
      <text x="120" y="146" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">bb + AE ft</text>`; },
    anim: FlowSketches.pulse,
  },

  jep_checkpoint: {
    tip: "Validation checkpoints the best epoch; early stopping reverts to it after the patience window.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="118" x2="216" y2="118"/>
      <line class="skl-axis" x1="28" y1="40" x2="28" y2="118"/>
      <path class="skl-draw c-cal" d="M30 52 L62 74 L94 62 L120 92 L150 80 L182 98 L210 90" style="fill:none"/>
      <circle class="sk-live skl-pop f-fin" cx="120" cy="92" r="5"/>
      <text x="120" y="110" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">best</text>
      <text x="200" y="60" text-anchor="end" style="fill:#7e8aa0;font-size:7px">val loss</text>`; },
    anim: FlowSketches.pulse,
  },

  jep_diag: {
    tip: "Inference reports four diagnostics: embedding MSE and cosine, plus decoder-only and full-chain curve MSE.",
    build(svg) {
      const rows = [["emb MSE", "f-cal", 66], ["cosine", "f-fin", 100], ["dec MSE", "f-cal", 48], ["chain MSE", "f-cal", 80]];
      let s = "";
      rows.forEach((r, i) => { const y = 38 + i * 24; s += `<text x="30" y="${y + 9}" style="fill:#7e8aa0;font-size:7px">${r[0]}</text><rect class="skl-pop ${r[1]}" x="104" y="${y}" width="${r[2]}" height="12" rx="2"/>`; });
      svg.innerHTML = s;
    },
    anim: null,
  },

  load: {
    tip: "The architecture is rebuilt from the saved config, the best-epoch weights load, x-axis and norm stats restore; the input must be one contiguous region.",
    build(svg) { svg.innerHTML = `
      <rect x="38" y="40" width="64" height="70" rx="4" class="skl-draw c-faint" style="fill:#1b242f"/>
      <rect x="48" y="52" width="44" height="6" rx="2" class="skl-pop f-meas"/>
      <rect x="48" y="64" width="44" height="6" rx="2" class="skl-pop f-meas"/>
      <rect x="48" y="76" width="44" height="6" rx="2" class="skl-pop f-meas"/>
      <rect x="48" y="88" width="44" height="6" rx="2" class="skl-pop f-meas"/>
      <text x="70" y="34" text-anchor="middle" style="fill:#6ea8ff;font-size:9px">theta*</text>
      <path class="skl-draw c-cal" d="M108 75 L150 75 M142 69 L150 75 L142 81" style="fill:none"/>
      <rect x="160" y="48" width="50" height="50" rx="3" class="skl-draw c-cal" style="fill:rgba(79,214,196,0.12)"/>
      <text x="185" y="118" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">1 region</text>`; },
    anim: null,
  },

  predict: {
    tip: "The frozen model emits raw normalised z-hat for every sliding-window patch in grid order, leaving no holes.",
    build(svg) {
      let g = "";
      for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) g += `<rect x="${44 + c * 34}" y="${40 + r * 28}" width="30" height="24" rx="2" style="fill:#1b242f;stroke:#303d4c"/>`;
      svg.innerHTML = `${g}<rect class="sk-live" x="44" y="40" width="30" height="24" rx="2" style="fill:rgba(110,168,255,0.25);stroke:#6ea8ff;stroke-width:2"/><text x="120" y="138" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">sliding window</text>`;
    },
    anim: FlowSketches.pulse,
  },

  idenorm: {
    tip: "Predictions are denormalised then hard-clamped (leaky_slope 0), pinning amplitude into [0, a_max].",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="40" y1="110" x2="210" y2="110"/>
      <line class="skl-axis" x1="40" y1="110" x2="40" y2="28"/>
      <line class="skl-dash c-faint" x1="40" y1="44" x2="210" y2="44"/>
      <text x="34" y="48" text-anchor="end" style="fill:#7e8aa0;font-size:7px">a_max</text>
      <path class="skl-dash c-mid" d="M30 124 L210 18" style="opacity:.3"/>
      <path class="skl-draw c-cal" d="M40 110 L100 110 L155 44 L210 44" style="fill:none"/>`; },
    anim: null,
  },

  align: {
    tip: "GT slots sort by mu (inactive last); the prediction keeps its raw order, so matching later resolves the correspondence.",
    build(svg) { svg.innerHTML = `
      <text x="60" y="34" text-anchor="middle" style="fill:#6ea8ff;font-size:8px">GT</text>
      <text x="180" y="34" text-anchor="middle" style="fill:#f5b971;font-size:8px">mu-sorted</text>
      <rect x="44" y="44" width="32" height="16" rx="2" class="skl-pop f-meas"/>
      <rect x="44" y="64" width="32" height="16" rx="2" class="skl-pop f-faint"/>
      <rect x="44" y="84" width="32" height="16" rx="2" class="skl-pop f-meas"/>
      <rect x="44" y="104" width="32" height="16" rx="2" class="skl-pop f-meas"/>
      <line class="skl-dash c-faint" x1="78" y1="52" x2="162" y2="52"/>
      <line class="skl-dash c-faint" x1="78" y1="72" x2="162" y2="112"/>
      <line class="skl-dash c-faint" x1="78" y1="92" x2="162" y2="72"/>
      <line class="skl-dash c-faint" x1="78" y1="112" x2="162" y2="92"/>
      <rect x="164" y="44" width="32" height="16" rx="2" class="skl-pop f-mid"/>
      <rect x="164" y="64" width="32" height="16" rx="2" class="skl-pop f-mid"/>
      <rect x="164" y="84" width="32" height="16" rx="2" class="skl-pop f-mid"/>
      <rect x="164" y="104" width="32" height="16" rx="2" class="skl-pop f-faint" style="opacity:.4"/>`; },
    anim: null,
  },

  recon: {
    tip: "Each patch's clamped Gaussians sum on the elevation axis, amplitudes rectified at zero, denominator 2 sigma^2 + 1e-8.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="34" y1="116" x2="214" y2="116"/>
      <path class="skl-draw c-faint" d="M34 116 C70 116 78 64 96 64 C114 64 122 116 158 116" style="fill:none;opacity:.4"/>
      <path class="skl-draw c-faint" d="M110 116 C140 116 148 80 162 80 C176 80 184 116 214 116" style="fill:none;opacity:.4"/>
      <path class="skl-draw c-mid" d="M34 116 C70 116 78 64 96 64 C108 64 116 92 134 92 C150 92 156 80 162 80 C176 80 184 116 214 116" style="fill:none"/>`; },
    anim: null,
  },

  window: {
    tip: "A separable Hann taper (each axis floored at 1e-3) gives every covered position a positive overlap-add weight.",
    build(svg) {
      let cells = "";
      for (let r = 0; r < 5; r++) for (let c = 0; c < 5; c++) { const d = Math.hypot(r - 2, c - 2) / 2.83; const op = (0.95 - d * 0.85).toFixed(2); cells += `<rect x="${150 + c * 12}" y="${40 + r * 12}" width="11" height="11" style="fill:#f5b971;opacity:${op}"/>`; }
      svg.innerHTML = `
        <line class="skl-axis" x1="40" y1="118" x2="120" y2="118"/>
        <path class="skl-draw c-mid" d="M40 118 C58 118 64 50 80 50 C96 50 102 118 120 118" style="fill:none"/>
        <text x="80" y="134" text-anchor="middle" style="fill:#f5b971;font-size:7px">Hann</text>
        ${cells}`;
    },
    anim: null,
  },

  ola: {
    tip: "Each windowed curve patch adds into accumulator A at its origin; the bare window adds into the weight buffer W.",
    build(svg) { svg.innerHTML = `
      <rect x="46" y="44" width="64" height="64" class="skl-axis" style="fill:#15302d"/>
      <text x="78" y="36" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">A += p w</text>
      <rect x="46" y="44" width="40" height="40" class="skl-pop f-cal" style="opacity:.5"/>
      <rect x="70" y="68" width="40" height="40" class="skl-pop f-cal" style="opacity:.5"/>
      <rect x="140" y="44" width="64" height="64" class="skl-axis" style="fill:#2a2418"/>
      <text x="172" y="36" text-anchor="middle" style="fill:#f5b971;font-size:8px">W += w</text>
      <rect x="140" y="44" width="40" height="40" class="skl-pop f-mid" style="opacity:.5"/>
      <rect x="164" y="68" width="40" height="40" class="skl-pop f-mid" style="opacity:.5"/>`; },
    anim: null,
  },

  finalise: {
    tip: "A is divided by W and the padding trimmed to the scene; a coverage guard aborts if any scene pixel got zero weight.",
    build(svg) { svg.innerHTML = `
      <rect x="38" y="52" width="44" height="44" class="skl-pop f-cal" style="opacity:.7"/>
      <text x="60" y="78" text-anchor="middle" style="fill:#0b1014;font-size:11px">A</text>
      <text x="98" y="80" text-anchor="middle" style="fill:#9fb0c0;font-size:16px">&#247;</text>
      <rect x="114" y="52" width="44" height="44" class="skl-pop f-mid" style="opacity:.7"/>
      <text x="136" y="80" text-anchor="middle" style="fill:#0b1014;font-size:11px">W</text>
      <text x="174" y="80" text-anchor="middle" style="fill:#9fb0c0;font-size:16px">=</text>
      <rect x="190" y="56" width="34" height="34" class="skl-draw c-fin" style="fill:rgba(196,163,255,0.15)"/>
      <text x="207" y="106" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">cube</text>`; },
    anim: null,
  },

  paramstitch: {
    tip: "Parameters are not blended: at each pixel the patch with the largest Hann centrality overwrites the value, then inactive GT mu/sigma go to NaN.",
    build(svg) { svg.innerHTML = `
      <rect x="40" y="40" width="74" height="74" class="skl-axis" style="fill:#1b242f"/>
      <rect x="40" y="40" width="46" height="46" class="skl-pop f-mid" style="opacity:.4"/>
      <rect x="68" y="68" width="46" height="46" class="skl-pop f-cal" style="opacity:.45"/>
      <circle class="sk-live skl-pop f-cal" cx="91" cy="77" r="5"/>
      <text x="77" y="130" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">centrality wins</text>
      <path class="skl-draw c-fin" d="M120 77 L152 77 M144 71 L152 77 L144 83" style="fill:none"/>
      <rect x="160" y="52" width="50" height="50" rx="3" class="skl-draw c-fin" style="fill:rgba(196,163,255,0.15)"/>
      <text x="185" y="118" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">params</text>`; },
    anim: FlowSketches.pulse,
  },

  pixelmaps: {
    tip: "Five per-pixel maps reduce over the elevation bins: MSE, MAE, R-squared, cosine similarity, and peak-bin error.",
    build(svg) {
      const vals = [0.9, 0.7, 0.95, 0.6, 0.8, 0.4, 0.85, 0.5, 0.92, 0.65, 0.75, 0.55];
      let cells = "";
      vals.forEach((v, i) => { const x = 120 + (i % 4) * 24, y = 44 + Math.floor(i / 4) * 24; cells += `<rect class="sk-live" x="${x}" y="${y}" width="22" height="22" style="fill:#4fd6c4;opacity:${0.2 + v * 0.6}"/>`; });
      svg.innerHTML = `
        <rect x="40" y="60" width="40" height="40" class="skl-draw c-faint" style="fill:#1b242f"/>
        <rect x="46" y="54" width="40" height="40" class="skl-draw c-faint" style="fill:#1b242f"/>
        <rect x="52" y="48" width="40" height="40" class="skl-draw c-meas" style="fill:#1d3350"/>
        <path class="skl-draw c-cal" d="M98 74 L112 74 M106 69 L112 74 L106 79" style="fill:none"/>
        ${cells}`;
    },
    anim: FlowSketches.pulse,
  },

  globalcurve: {
    tip: "Cube-wide scalars at physical scale: MSE, RMSE, R-squared, and a PSNR over the GT range C_max - C_min.",
    build(svg) { svg.innerHTML = `
      <rect x="40" y="40" width="160" height="70" rx="5" class="skl-axis" style="fill:#1b242f"/>
      <text x="58" y="64" style="fill:#9fb0c0;font-size:11px">R2</text>
      <text x="184" y="64" text-anchor="end" style="fill:#c4a3ff;font-size:13px;font-weight:600">0.94</text>
      <line x1="56" y1="74" x2="184" y2="74" class="skl-axis"/>
      <text x="58" y="96" style="fill:#9fb0c0;font-size:11px">PSNR</text>
      <text x="184" y="96" text-anchor="end" style="fill:#4fd6c4;font-size:13px;font-weight:600">28.4 dB</text>`; },
    anim: null,
  },

  elevssim: {
    tip: "Per elevation bin: MAE, RMSE, R-squared and a column-normalised cross-entropy, plus mean SSIM over the slices.",
    build(svg) {
      const h = [20, 34, 46, 40, 28, 18];
      let b = "";
      h.forEach((v, i) => { b += `<rect class="skl-pop f-cal" x="${44 + i * 16}" y="${108 - v}" width="11" height="${v}" rx="1"/>`; });
      svg.innerHTML = `<line class="skl-axis" x1="40" y1="108" x2="148" y2="108"/>${b}<text x="92" y="124" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">R2 per bin</text><rect x="162" y="44" width="52" height="52" class="skl-axis" style="fill:#1b242f"/><rect x="162" y="62" width="52" height="9" class="skl-pop f-fin"/><text x="188" y="110" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">SSIM</text>`;
    },
    anim: null,
  },

  paramslot: {
    tip: "On active pixels, per-Gaussian mu/sigma errors and detection F1 pool after brute-force optimal mu-matching over all K! permutations.",
    build(svg) { svg.innerHTML = `
      <circle cx="60" cy="58" r="9" class="skl-dash c-meas" style="fill:none"/>
      <circle cx="60" cy="58" r="4" class="skl-pop f-cal"/>
      <text x="60" y="84" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">mu err</text>
      <line class="skl-axis" x1="104" y1="100" x2="196" y2="100"/>
      <rect x="110" y="86" width="14" height="14" class="skl-pop f-faint"/>
      <rect x="132" y="60" width="14" height="40" class="skl-pop f-fin"/>
      <rect x="154" y="90" width="14" height="10" class="skl-pop f-faint"/>
      <rect x="176" y="84" width="14" height="16" class="skl-pop f-faint"/>
      <text x="150" y="50" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">best perm</text>`; },
    anim: null,
  },

  reduced: {
    tip: "A reduced Capon tomogram is re-synthesised; GT, prediction and reduced cubes are area-normalised and the MSE gain mapped.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="40" y1="100" x2="150" y2="100"/>
      <path class="skl-draw c-meas" d="M40 100 C66 100 72 48 95 48 C118 48 124 100 150 100" style="fill:none"/>
      <path class="skl-draw c-fin" d="M40 100 C68 100 74 56 95 56 C116 56 122 100 150 100" style="fill:none"/>
      <path class="skl-draw c-mid" d="M40 100 C62 100 70 74 88 70 C108 66 118 100 150 100" style="fill:none"/>
      <text x="40" y="34" style="fill:#6ea8ff;font-size:7px">GT</text>
      <text x="74" y="34" style="fill:#c4a3ff;font-size:7px">pred</text>
      <text x="112" y="34" style="fill:#f5b971;font-size:7px">reduced</text>
      <rect x="166" y="46" width="48" height="48" class="skl-pop f-fin" style="opacity:.6"/>
      <text x="190" y="108" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">delta MSE</text>`; },
    anim: null,
  },

  consistency: {
    tip: "Curves are reprojected to track coherences via kz; the measured multilooked phase should agree with the synthesised one, not its flip.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="36" y1="104" x2="104" y2="104"/>
      <path class="skl-draw c-cal" d="M36 104 C54 104 60 52 70 52 C80 52 86 104 104 104" style="fill:none"/>
      <text x="70" y="120" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">curve, kz</text>
      <circle cx="150" cy="66" r="22" class="skl-dash c-faint" style="fill:none"/>
      <line class="skl-draw c-meas" x1="150" y1="66" x2="170" y2="55" style="fill:none"/>
      <line class="sk-live skl-draw c-cal" x1="150" y1="66" x2="166" y2="50" style="fill:none"/>
      <text x="150" y="102" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">meas vs synth</text>
      <rect x="188" y="44" width="44" height="44" class="skl-pop f-fin" style="opacity:.6"/>
      <text x="210" y="100" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">E_gamma</text>`; },
    anim: FlowSketches.pulse,
  },

  paei_restore: {
    tip: "The run is rebuilt strictly from run_summary.json; it aborts unless model_name is profile_ae, and profile length L must match everywhere.",
    build(svg) { svg.innerHTML = `
      <rect x="28" y="54" width="42" height="44" rx="3" class="skl-pop f-meas"/>
      <text x="49" y="80" text-anchor="middle" style="fill:#0b1014;font-size:9px">&#952;*</text>
      <text x="86" y="82" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <path class="skl-draw c-faint" d="M108 40 L150 62 L150 90 L108 112 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M192 40 L150 62 L150 90 L192 112 Z" style="fill:none"/>
      <circle cx="150" cy="76" r="4" class="skl-pop f-cal"/>
      <path class="skl-draw c-cal" d="M110 30 L120 40 L138 20" style="fill:none;stroke-width:2"/>
      <text x="150" y="130" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">profile_ae</text>`; },
    anim: null,
  },

  paei_select: {
    tip: "Active pixels (peak > tau_a = 1e-3) are all kept; a 5% sample of empty pixels comes along, then the index is shuffled.",
    build(svg) {
      const act = new Set([0, 1, 3, 4, 6, 7, 9, 10, 12, 15, 16, 18]);
      const kept = new Set([5, 13]);
      let s = "";
      for (let i = 0; i < 20; i++) {
        const x = 40 + (i % 5) * 32, y = 32 + Math.floor(i / 5) * 26;
        const a = act.has(i);
        s += `<rect class="skl-pop ${a ? "f-cal" : "f-faint"}" x="${x}" y="${y}" width="24" height="18" rx="2" style="opacity:${a ? 1 : 0.4}"/>`;
        if (kept.has(i)) s += `<rect class="sk-live" x="${x}" y="${y}" width="24" height="18" rx="2" style="fill:none;stroke:#4fd6c4;stroke-width:2"/>`;
      }
      svg.innerHTML = s + `<text x="120" y="146" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">active + 5% empties</text>`;
    },
    anim: FlowSketches.pulse,
  },

  paei_curves: {
    tip: "Each kept pixel's profile is rebuilt as a sum of its K Gaussians on the elevation axis; sigma floored 1e-6, exponent clipped.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="24" y1="118" x2="216" y2="118"/>
      <path class="skl-draw c-faint" d="M30 118 Q66 60 102 118" style="fill:none;opacity:.45"/>
      <path class="skl-draw c-faint" d="M120 118 Q152 44 184 118" style="fill:none;opacity:.45"/>
      <path class="skl-draw c-cal" d="M30 118 Q66 62 102 104 Q140 60 168 96 Q184 100 206 118" style="fill:none"/>
      <text x="120" y="30" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">c = &#8721; a_k G(mu_k, sig_k)</text>`; },
    anim: null,
  },

  paei_normalise: {
    tip: "log1p compresses the profile, then subtract the train loc and divide by the train scale (floored 1e-6) into network units.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="104" x2="214" y2="104"/>
      <line class="skl-dash c-faint" x1="120" y1="30" x2="120" y2="112"/>
      <text x="120" y="124" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">0</text>
      <path class="skl-draw c-faint" d="M150 104 C164 56 198 56 210 104" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-cal" d="M84 104 C100 44 132 44 148 104" style="fill:none"/>
      <text x="118" y="26" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">(log1p(c) - l)/s</text>`; },
    anim: null,
  },

  paei_reshape: {
    tip: "The length-L profile is cast to L channels over a 1x1 cell, so the profile axis becomes the conv-MLP channel axis.",
    build(svg) {
      let s = "";
      for (let i = 0; i < 8; i++) s += `<rect class="skl-pop f-cal" x="148" y="${30 + i * 12}" width="20" height="10" rx="1.5" style="opacity:${(0.4 + 0.07 * i).toFixed(2)}"/>`;
      svg.innerHTML = `
        <line class="skl-axis" x1="24" y1="104" x2="98" y2="104"/>
        <path class="skl-draw c-mid" d="M24 100 Q44 50 60 80 Q76 96 98 62" style="fill:none"/>
        <text x="58" y="122" text-anchor="middle" style="fill:#f5b971;font-size:7px">c_n : L</text>
        <text x="112" y="80" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
        ${s}
        <text x="158" y="140" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">L x 1 x 1</text>`;
    },
    anim: null,
  },

  paei_encode: {
    tip: "The encoder MLP contracts L profile channels to a d-dim latent; embedding-norm (default layernorm) standardises it.",
    build(svg) { svg.innerHTML = `
      <rect x="24" y="40" width="14" height="70" rx="2" class="skl-pop f-mid" style="opacity:.8"/>
      <rect x="40" y="46" width="14" height="58" rx="2" class="skl-pop f-mid" style="opacity:.8"/>
      <path class="skl-draw c-faint" d="M64 44 L120 66 L120 86 L64 106 Z" style="fill:none"/>
      <rect class="sk-live skl-pop f-cal" x="150" y="58" width="30" height="9" rx="2"/>
      <rect class="sk-live skl-pop f-cal" x="150" y="70" width="30" height="9" rx="2" style="opacity:.8"/>
      <rect class="sk-live skl-pop f-cal" x="150" y="82" width="30" height="9" rx="2" style="opacity:.6"/>
      <text x="165" y="108" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">z : d=24</text>`; },
    anim: FlowSketches.pulse,
  },

  paei_decode: {
    tip: "The decoder MLP expands the latent back to L channels, reconstructing the profile in normalised space.",
    build(svg) { svg.innerHTML = `
      <rect x="30" y="58" width="26" height="9" rx="2" class="skl-pop f-cal"/>
      <rect x="30" y="70" width="26" height="9" rx="2" class="skl-pop f-cal" style="opacity:.8"/>
      <rect x="30" y="82" width="26" height="9" rx="2" class="skl-pop f-cal" style="opacity:.6"/>
      <path class="skl-draw c-faint" d="M120 44 L64 66 L64 86 L120 106 Z" style="fill:none"/>
      <line class="skl-axis" x1="140" y1="112" x2="214" y2="112"/>
      <path class="skl-draw c-mid" d="M140 108 Q166 52 182 84 Q196 100 214 70" style="fill:none"/>
      <text x="178" y="128" text-anchor="middle" style="fill:#f5b971;font-size:8px">c-hat_n : L</text>`; },
    anim: null,
  },

  paei_denorm: {
    tip: "expm1 inverts log1p after the log-domain value is clipped to [0, log1p(1000)], bounding the physical profile to [0, 1000].",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="106" x2="214" y2="106"/>
      <line class="skl-dash c-mid" x1="30" y1="44" x2="214" y2="44"/>
      <text x="208" y="40" text-anchor="end" style="fill:#f5b971;font-size:7px">log1p(1000)</text>
      <path class="skl-draw c-meas" d="M40 106 C78 58 150 50 200 50" style="fill:none;opacity:.55"/>
      <path class="skl-draw c-cal" d="M40 106 C74 52 150 46 200 46" style="fill:none"/>
      <text x="120" y="128" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">expm1(clip(x s + l))</text>`; },
    anim: null,
  },

  paei_embed: {
    tip: "The per-profile latents stack into the N x d embedding matrix Z, saved to embeddings.npy.",
    build(svg) {
      let m = "";
      for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) {
        const x = 36 + c * 18, y = 40 + r * 16;
        m += `<rect class="sk-live skl-pop f-fin" x="${x}" y="${y}" width="15" height="13" rx="1.5" style="opacity:${(0.35 + 0.11 * ((r + c) % 5)).toFixed(2)}"/>`;
      }
      svg.innerHTML = m + `
        <text x="66" y="128" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">Z : N x d</text>
        <text x="140" y="80" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
        <rect x="168" y="46" width="44" height="56" rx="3" class="skl-draw c-fin" style="fill:rgba(196,163,255,0.10)"/>
        <text x="190" y="78" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">.npy</text>`;
    },
    anim: FlowSketches.pulse,
  },

  paei_physical: {
    tip: "Reconstruction vs GT profiles score MSE, RMSE, MAE and R2 (1e-8 stabiliser) at physical scale.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="26" y1="112" x2="214" y2="112"/>
      <path class="skl-draw c-meas" d="M30 110 Q70 46 104 96 Q140 40 176 92 Q192 100 210 108" style="fill:none;opacity:.55"/>
      <path class="skl-draw c-cal" d="M30 110 Q70 52 104 100 Q140 46 176 96 Q192 102 210 110" style="fill:none"/>
      <line class="sk-live skl-pop" x1="70" y1="46" x2="70" y2="54" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <line class="sk-live skl-pop" x1="140" y1="40" x2="140" y2="48" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <text x="120" y="28" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">R2 = 1 - SSE/SST</text>`; },
    anim: FlowSketches.pulse,
  },

  paei_shape: {
    tip: "On active curves: the mean-centred Pearson correlation and relative-L2 measure magnitude-free profile shape.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="26" y1="80" x2="214" y2="80"/>
      <path class="skl-draw c-cal" d="M30 74 Q66 20 96 66 Q126 30 156 70 Q184 84 214 60" style="fill:none"/>
      <path class="skl-dash c-meas" d="M30 78 Q66 26 96 68 Q126 36 156 72 Q184 82 214 64" style="fill:none;opacity:.6"/>
      <text x="120" y="130" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">rho, relL2</text>`; },
    anim: null,
  },

  paei_power: {
    tip: "Integrated power is the trapezoidal area under each curve; peak-location MAE is the gap between the argmax elevations.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="26" y1="114" x2="214" y2="114"/>
      <path class="skl-draw c-cal" d="M40 114 Q92 30 120 30 Q150 30 200 114 Z" style="fill:rgba(79,214,196,0.14)"/>
      <path class="skl-dash c-meas" d="M46 114 Q96 46 122 46 Q150 46 196 114" style="fill:none;opacity:.6"/>
      <line class="skl-dash c-faint" x1="120" y1="30" x2="120" y2="114"/>
      <circle cx="120" cy="30" r="3.5" class="skl-pop f-cal"/>
      <text x="120" y="24" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">peak</text>
      <text x="150" y="90" style="fill:#4fd6c4;font-size:7px">power</text>`; },
    anim: null,
  },

  paei_embstat: {
    tip: "Per-dimension embedding std vs the 1e-4 collapse threshold; the active fraction counts dims that clear it.",
    build(svg) {
      const hs = [40, 52, 10, 46, 6, 38, 50, 8, 44, 30];
      let b = "";
      hs.forEach((h, i) => { const x = 40 + i * 17, a = h > 16; b += `<rect class="skl-pop ${a ? "f-cal" : "f-faint"}" x="${x}" y="${112 - h}" width="12" height="${h}" style="opacity:${a ? 0.9 : 0.5}"/>`; });
      svg.innerHTML = `
        <line class="skl-axis" x1="32" y1="112" x2="214" y2="112"/>
        <line class="skl-dash c-mid" x1="32" y1="96" x2="214" y2="96"/>
        <text x="34" y="92" style="fill:#f5b971;font-size:7px">1e-4</text>
        ${b}
        <text x="120" y="30" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">per-dim std</text>`;
    },
    anim: null,
  },

  paei_report: {
    tip: "Metrics land in metrics.json; ranked reconstructions, mean profile, error/embedding histograms and a power scatter fill report.md.",
    build(svg) { svg.innerHTML = `
      <rect x="30" y="26" width="92" height="100" rx="3" class="skl-draw c-fin" style="fill:rgba(196,163,255,0.06)"/>
      <line x1="40" y1="42" x2="112" y2="42" style="stroke:#c4a3ff;stroke-width:2;opacity:.7"/>
      <line x1="40" y1="54" x2="104" y2="54" style="stroke:#7e8aa0;stroke-width:1.5;opacity:.6"/>
      <line x1="40" y1="64" x2="108" y2="64" style="stroke:#7e8aa0;stroke-width:1.5;opacity:.6"/>
      <line x1="40" y1="74" x2="98" y2="74" style="stroke:#7e8aa0;stroke-width:1.5;opacity:.6"/>
      <text x="76" y="120" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">report.md</text>
      <rect x="140" y="30" width="72" height="42" rx="2" class="skl-pop f-faint" style="opacity:.25"/>
      <path class="skl-draw c-cal" d="M146 66 Q168 36 176 52 Q186 66 206 40" style="fill:none"/>
      <rect x="140" y="82" width="72" height="42" rx="2" class="skl-pop f-faint" style="opacity:.25"/>
      <circle cx="156" cy="112" r="2.4" class="skl-pop f-cal"/>
      <circle cx="170" cy="104" r="2.4" class="skl-pop f-cal"/>
      <circle cx="184" cy="98" r="2.4" class="skl-pop f-cal"/>
      <circle cx="198" cy="92" r="2.4" class="skl-pop f-cal"/>
      <text x="176" y="120" text-anchor="middle" style="fill:#7e8aa0;font-size:6px">figures</text>`; },
    anim: null,
  },

  iaei_loadrun: {
    tip: "run_summary must say model_name = image_ae; the AE is rebuilt and best_model.pt weights loaded in eval.",
    build(svg) { svg.innerHTML = `
      <rect x="26" y="52" width="30" height="46" rx="3" class="skl-pop f-meas"/>
      <text x="41" y="112" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">ckpt</text>
      <path class="skl-dash c-meas" d="M58 75 L74 75 M68 71 L74 75 L68 79" style="fill:none"/>
      <path class="skl-draw c-faint" d="M80 46 L120 62 L120 90 L80 106 Z" style="fill:none"/>
      <path class="skl-draw c-faint" d="M128 62 L168 46 L168 106 L128 90 Z" style="fill:none"/>
      <text x="124" y="126" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">Enc | Dec</text>
      <text x="196" y="79" text-anchor="middle" style="fill:#6ea8ff;font-size:10px">&#952;*</text>`; },
    anim: null,
  },

  iaei_stats: {
    tip: "Only the per-channel input loc and scale are kept; the output-parameter stats are dropped.",
    build(svg) { svg.innerHTML = `
      <text x="58" y="34" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">input stats</text>
      <line class="skl-axis" x1="26" y1="102" x2="88" y2="102"/>
      <rect x="30" y="42" width="14" height="60" class="skl-pop f-meas"/>
      <rect x="48" y="58" width="14" height="44" class="skl-pop f-meas"/>
      <rect x="66" y="50" width="14" height="52" class="skl-pop f-meas"/>
      <text x="58" y="116" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">mu_c , s_c</text>
      <text x="168" y="34" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">output stats</text>
      <rect x="140" y="52" width="54" height="46" rx="3" class="skl-pop f-faint" style="opacity:.35"/>
      <line class="skl-dash c-faint" x1="140" y1="52" x2="194" y2="98"/>
      <text x="167" y="118" text-anchor="middle" style="fill:#7e8aa0;font-size:9px">&#8709;</text>`; },
    anim: null,
  },

  iaei_dataset: {
    tip: "The split (default test) must be one contiguous region; it tiles into PxP normalised patches, channels matching training.",
    build(svg) {
      let g = "";
      for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) g += `<rect x="${44 + c * 38}" y="${32 + r * 30}" width="37" height="29" class="skl-pop f-meas" style="opacity:.14;stroke:#6ea8ff;stroke-width:.8"/>`;
      svg.innerHTML = `${g}<rect class="sk-live" x="82" y="62" width="37" height="29" style="fill:none;stroke:#4fd6c4;stroke-width:2.2"/><text x="120" y="138" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">test region &#8594; x-hat patches</text>`;
    },
    anim: FlowSketches.pulse,
  },

  iaei_encode: {
    tip: "no_grad encoder maps the patch to a latent, then the embedding norm (none, L2 eps 1e-6, or layernorm) is applied.",
    build(svg) { svg.innerHTML = `
      <rect x="26" y="52" width="34" height="46" class="skl-pop f-meas"/>
      <text x="43" y="112" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">x-hat</text>
      <path class="skl-draw c-faint" d="M74 50 L128 66 L128 88 L74 104 Z" style="fill:none"/>
      <text x="100" y="120" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">Enc</text>
      <rect class="sk-live skl-pop f-mid" x="150" y="60" width="16" height="16"/>
      <rect class="sk-live skl-pop f-mid" x="168" y="60" width="16" height="16"/>
      <rect class="sk-live skl-pop f-mid" x="150" y="78" width="16" height="16"/>
      <rect class="sk-live skl-pop f-mid" x="168" y="78" width="16" height="16"/>
      <text x="167" y="110" text-anchor="middle" style="fill:#f5b971;font-size:8px">z</text>`; },
    anim: FlowSketches.pulse,
  },

  iaei_decode: {
    tip: "The decoder widens the latent back to a normalised reconstruction with the same channels and PxP size.",
    build(svg) { svg.innerHTML = `
      <rect class="skl-pop f-mid" x="30" y="60" width="16" height="16"/>
      <rect class="skl-pop f-mid" x="48" y="60" width="16" height="16"/>
      <rect class="skl-pop f-mid" x="30" y="78" width="16" height="16"/>
      <rect class="skl-pop f-mid" x="48" y="78" width="16" height="16"/>
      <text x="47" y="110" text-anchor="middle" style="fill:#f5b971;font-size:8px">z</text>
      <path class="skl-draw c-faint" d="M82 66 L136 50 L136 104 L82 88 Z" style="fill:none"/>
      <text x="110" y="120" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">Dec</text>
      <rect x="158" y="50" width="46" height="54" class="skl-pop f-mid" style="opacity:.85"/>
      <text x="181" y="118" text-anchor="middle" style="fill:#f5b971;font-size:7px">x-hat_n</text>`; },
    anim: null,
  },

  iaei_denorm: {
    tip: "Both tensors invert with the input stats: scale, shift, and for log1p slots expm1 after clipping the argument to [0, log 1001].",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="106" x2="214" y2="106"/>
      <line class="skl-axis" x1="30" y1="24" x2="30" y2="106"/>
      <line class="skl-dash c-mid" x1="30" y1="44" x2="214" y2="44"/>
      <text x="208" y="40" text-anchor="end" style="fill:#f5b971;font-size:7px">log 1001</text>
      <path class="skl-draw c-cal" d="M40 104 C86 60 150 46 200 46" style="fill:none"/>
      <text x="120" y="126" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">expm1(clip(x-hat s + mu, 0, log 1001))</text>`; },
    anim: null,
  },

  iaei_embed: {
    tip: "Each patch embedding is the latent averaged over its spatial dimensions, a global mean pool to a D-vector.",
    build(svg) {
      const m = FlowSketches.grid(3, (r, c) => `<rect class="sk-live skl-pop f-mid" x="${40 + c * 22}" y="${44 + r * 22}" width="20" height="20" style="opacity:.7"/>`);
      svg.innerHTML = `${m}
        <text x="118" y="80" text-anchor="middle" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
        <rect x="150" y="44" width="18" height="62" class="skl-pop f-cal"/>
        <text x="159" y="120" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">z-bar</text>
        <text x="72" y="122" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">mean over h,w</text>`;
    },
    anim: FlowSketches.pulse,
  },

  iaei_residual: {
    tip: "The residual is the elementwise pred minus gt in physical units; every metric reduces it.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="28" y1="80" x2="216" y2="80"/>
      <path class="skl-draw c-cal" d="M30 70 Q60 34 92 58 Q124 24 156 52 Q184 46 214 68" style="fill:none"/>
      <path class="skl-dash c-cal" d="M30 74 Q60 44 92 62 Q124 34 156 58 Q184 54 214 72" style="fill:none;opacity:.55"/>
      <line class="sk-live skl-pop" x1="60" y1="40" x2="60" y2="52" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <line class="sk-live skl-pop" x1="124" y1="27" x2="124" y2="37" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <line class="sk-live skl-pop" x1="156" y1="53" x2="156" y2="61" style="stroke:#f5b971;stroke-width:3;opacity:1"/>
      <text x="120" y="122" text-anchor="middle" style="fill:#f5b971;font-size:7px">e = x-tilde - x</text>`; },
    anim: FlowSketches.pulse,
  },

  iaei_physical: {
    tip: "Predicted against GT scatter along the identity line; R2, PSNR and MSE quantify the spread (1e-8 stabiliser).",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="40" y1="118" x2="40" y2="26"/>
      <line class="skl-axis" x1="40" y1="118" x2="206" y2="118"/>
      <line class="skl-dash c-faint" x1="40" y1="118" x2="200" y2="34"/>
      <circle cx="72" cy="98" r="3" class="skl-pop f-cal"/>
      <circle cx="100" cy="82" r="3" class="skl-pop f-cal"/>
      <circle cx="128" cy="68" r="3" class="skl-pop f-cal"/>
      <circle cx="150" cy="56" r="3" class="skl-pop f-cal"/>
      <circle cx="176" cy="46" r="3" class="skl-pop f-cal"/>
      <text x="198" y="30" text-anchor="end" style="fill:#7e8aa0;font-size:7px">y = x</text>
      <text x="58" y="42" style="fill:#4fd6c4;font-size:9px">R2, PSNR</text>
      <text x="52" y="128" style="fill:#6ea8ff;font-size:7px">GT</text>`; },
    anim: null,
  },

  iaei_normalized: {
    tip: "The physical GT and prediction are re-normalised with the input stats and their MSE recomputed dimensionless.",
    build(svg) { svg.innerHTML = `
      <rect x="26" y="52" width="42" height="46" rx="3" class="skl-pop f-cal"/>
      <text x="47" y="79" text-anchor="middle" style="fill:#0b1014;font-size:8px">phys</text>
      <path class="skl-draw c-mid" d="M74 75 L150 75 M142 69 L150 75 L142 81" style="fill:none"/>
      <text x="112" y="68" text-anchor="middle" style="fill:#f5b971;font-size:7px">(f-mu)/s</text>
      <rect x="158" y="52" width="42" height="46" rx="3" class="skl-pop f-meas"/>
      <text x="179" y="79" text-anchor="middle" style="fill:#0b1014;font-size:8px">norm</text>
      <text x="120" y="120" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">MSE_n dimensionless</text>`; },
    anim: null,
  },

  iaei_channel: {
    tip: "Averaging the squared residual over patches and space, per channel, shows which passes reconstruct worst.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="116" x2="214" y2="116"/>
      <rect x="40" y="76" width="18" height="40" class="skl-pop f-cal"/>
      <rect x="66" y="58" width="18" height="58" class="skl-pop f-cal"/>
      <rect x="92" y="92" width="18" height="24" class="skl-pop f-cal"/>
      <rect x="118" y="70" width="18" height="46" class="skl-pop f-cal"/>
      <rect x="144" y="48" width="18" height="68" class="sk-live skl-pop f-mid"/>
      <rect x="170" y="86" width="18" height="30" class="skl-pop f-cal"/>
      <rect x="196" y="80" width="14" height="36" class="skl-pop f-faint"/>
      <text x="120" y="132" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">m_c per channel</text>`; },
    anim: FlowSketches.pulse,
  },

  iaei_embstats: {
    tip: "Per-dimension std bars against the 1e-4 line: bars above it count as active dimensions, below as collapsed.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="112" x2="214" y2="112"/>
      <line class="skl-dash c-mid" x1="30" y1="96" x2="214" y2="96"/>
      <text x="34" y="92" style="fill:#f5b971;font-size:7px">1e-4</text>
      <rect x="40" y="52" width="14" height="60" class="skl-pop f-cal"/>
      <rect x="60" y="44" width="14" height="68" class="skl-pop f-cal"/>
      <rect x="80" y="64" width="14" height="48" class="skl-pop f-cal"/>
      <rect x="100" y="58" width="14" height="54" class="skl-pop f-cal"/>
      <rect x="120" y="100" width="14" height="12" class="skl-pop f-faint"/>
      <rect x="140" y="102" width="14" height="10" class="skl-pop f-faint"/>
      <rect x="160" y="50" width="14" height="62" class="skl-pop f-cal"/>
      <rect x="180" y="70" width="14" height="42" class="skl-pop f-cal"/>
      <text x="120" y="130" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">sigma_d , active fraction</text>`; },
    anim: null,
  },

  iaei_persist: {
    tip: "Embeddings go to embeddings.npy, the metric dict to metrics.json, and a Markdown report is assembled.",
    build(svg) { svg.innerHTML = `
      <rect x="34" y="42" width="44" height="58" rx="3" class="skl-pop f-fin"/>
      <line class="skl-dash c-faint" x1="44" y1="56" x2="68" y2="56"/>
      <line class="skl-dash c-faint" x1="44" y1="66" x2="68" y2="66"/>
      <text x="56" y="114" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">embeddings</text>
      <rect x="98" y="42" width="44" height="58" rx="3" class="skl-pop f-fin" style="opacity:.8"/>
      <line class="skl-dash c-faint" x1="108" y1="56" x2="132" y2="56"/>
      <text x="120" y="114" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">metrics.json</text>
      <rect x="162" y="42" width="44" height="58" rx="3" class="skl-pop f-fin" style="opacity:.6"/>
      <line class="skl-dash c-faint" x1="172" y1="56" x2="196" y2="56"/>
      <text x="184" y="114" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">report.md</text>`; },
    anim: null,
  },

  bench_reference: {
    tip: "The reference model (unet) at default width sets N*, the parameter budget every architecture must match.",
    build(svg) { svg.innerHTML = `
      <path class="skl-draw c-meas" d="M34 46 L74 58 L74 92 L34 104 Z" style="fill:none"/>
      <text x="54" y="122" text-anchor="middle" style="fill:#6ea8ff;font-size:8px">unet</text>
      <text x="96" y="78" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect class="sk-live skl-pop f-cal" x="118" y="64" width="94" height="20" rx="2"/>
      <text x="165" y="58" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">N* (budget)</text>
      <text x="165" y="78" text-anchor="middle" style="fill:#0b1014;font-size:8px">params</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_search: {
    tip: "Scale is bisected by geometric mean s = sqrt(l h); the candidate count converges onto the budget N*.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="100" x2="214" y2="100"/>
      <line class="skl-axis" x1="40" y1="95" x2="40" y2="105"/>
      <line class="skl-axis" x1="196" y1="95" x2="196" y2="105"/>
      <text x="40" y="118" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">l</text>
      <text x="196" y="118" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">h</text>
      <line class="skl-dash c-cal" x1="132" y1="42" x2="132" y2="104"/>
      <text x="132" y="36" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">N*</text>
      <circle class="sk-live skl-pop f-mid" cx="120" cy="100" r="4.5"/>
      <text x="120" y="128" text-anchor="middle" style="fill:#f5b971;font-size:7px">s = sqrt(l h)</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_widths: {
    tip: "The scaled width is rounded to the divisor 8 and floored there; locked embedding dims are never scaled.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="46" y1="120" x2="204" y2="120"/>
      <line class="skl-dash c-faint" x1="46" y1="98" x2="204" y2="98" style="opacity:.35"/>
      <line class="skl-dash c-faint" x1="46" y1="76" x2="204" y2="76" style="opacity:.35"/>
      <line class="skl-dash c-faint" x1="46" y1="54" x2="204" y2="54" style="opacity:.35"/>
      <rect class="skl-pop f-cal" x="56" y="76" width="18" height="44"/>
      <rect class="skl-pop f-cal" x="86" y="54" width="18" height="66"/>
      <rect class="sk-live skl-pop f-cal" x="116" y="98" width="18" height="22"/>
      <rect class="skl-pop f-cal" x="146" y="76" width="18" height="44"/>
      <rect class="skl-pop f-faint" x="176" y="54" width="18" height="66" style="opacity:.5"/>
      <text x="185" y="50" text-anchor="middle" style="fill:#7e8aa0;font-size:6px">locked</text>
      <text x="204" y="134" text-anchor="end" style="fill:#4fd6c4;font-size:7px">round&#183;8</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_context: {
    tip: "After a cache clear, resident memory (total - free) is the CUDA context added to every peak; >1.5 GB warns.",
    build(svg) { svg.innerHTML = `
      <rect class="skl-draw c-faint" x="92" y="30" width="56" height="100" rx="2" style="fill:none"/>
      <line class="skl-dash c-cal" x1="84" y1="44" x2="156" y2="44"/>
      <text x="156" y="40" text-anchor="end" style="fill:#4fd6c4;font-size:7px">budget 40 GB</text>
      <rect class="sk-live skl-pop f-meas" x="92" y="114" width="56" height="16"/>
      <text x="120" y="126" text-anchor="middle" style="fill:#0b1014;font-size:7px">C_ctx</text>
      <text x="120" y="24" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">device VRAM</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_probe: {
    tip: "Each doubling batch runs a real 3-step train loop; peak reserved VRAM plus context is the measured footprint.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="122" x2="214" y2="122"/>
      <line class="skl-dash c-cal" x1="30" y1="44" x2="214" y2="44"/>
      <text x="212" y="40" text-anchor="end" style="fill:#4fd6c4;font-size:7px">40 GB</text>
      <rect class="skl-pop f-mid" x="42" y="108" width="20" height="14"/>
      <rect class="skl-pop f-mid" x="72" y="94" width="20" height="28"/>
      <rect class="skl-pop f-mid" x="102" y="76" width="20" height="46"/>
      <rect class="sk-live skl-pop f-mid" x="132" y="52" width="20" height="70"/>
      <rect class="skl-pop f-faint" x="162" y="30" width="20" height="92" style="opacity:.5"/>
      <text x="120" y="138" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">b = 1, 2, 4, 8, 16</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_maxbatch: {
    tip: "The largest batch whose bar stays under the budget line is kept as B*; the scan stops at the first over/OOM.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="122" x2="214" y2="122"/>
      <line class="skl-dash c-cal" x1="30" y1="52" x2="214" y2="52"/>
      <text x="212" y="48" text-anchor="end" style="fill:#4fd6c4;font-size:7px">budget</text>
      <rect class="skl-pop f-cal" x="42" y="108" width="20" height="14" style="opacity:.6"/>
      <rect class="skl-pop f-cal" x="72" y="92" width="20" height="30" style="opacity:.75"/>
      <rect class="skl-pop f-cal" x="102" y="72" width="20" height="50" style="opacity:.85"/>
      <rect class="sk-live skl-pop f-cal" x="132" y="58" width="20" height="64"/>
      <rect x="130" y="56" width="24" height="68" class="sk-live" style="fill:none;stroke:#4fd6c4;stroke-width:2"/>
      <rect class="skl-pop f-faint" x="162" y="34" width="20" height="88" style="opacity:.35"/>
      <text x="142" y="50" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">B*</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_units: {
    tip: "The grid is models x loss components x seeds; each cell is one trained/inferred benchmark unit.",
    build(svg) {
      let g = "";
      for (let r = 0; r < 4; r++) for (let c = 0; c < 3; c++) { const x = 74 + c * 42, y = 40 + r * 22; g += `<rect class="skl-pop f-cal" x="${x}" y="${y}" width="34" height="16" rx="2" style="opacity:${0.55 + 0.1 * c}"/>`; }
      svg.innerHTML = `
        <text x="132" y="30" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">models x components x seeds</text>
        ${g}
        <rect x="72" y="38" width="122" height="20" class="sk-live" style="fill:none;stroke:#4fd6c4;stroke-width:2"/>
        <text x="52" y="52" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">m1</text>`;
    },
    anim: FlowSketches.pulse,
  },

  bench_train: {
    tip: "Each unit trains at matched width and measured batch; the best-epoch val-loss minimum is checkpointed.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="34" y1="120" x2="212" y2="120"/>
      <line class="skl-axis" x1="34" y1="30" x2="34" y2="120"/>
      <path class="skl-draw c-faint" d="M40 44 C80 96 130 108 206 112" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-faint" d="M40 52 C84 100 140 100 206 104" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-cal" d="M40 40 C82 92 120 96 150 90 C176 86 194 88 206 90" style="fill:none"/>
      <circle class="sk-live skl-pop f-cal" cx="150" cy="90" r="4.5"/>
      <text x="150" y="82" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">best</text>
      <text x="120" y="136" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">val loss / epoch</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_infer: {
    tip: "Sliding-window inference on the held-out test split yields the scalar metric vector q for the unit.",
    build(svg) { svg.innerHTML = `
      <rect x="30" y="48" width="96" height="56" rx="2" class="skl-pop f-faint" style="opacity:.35"/>
      <text x="78" y="118" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">test split</text>
      <rect class="sk-live" x="42" y="58" width="30" height="36" style="fill:none;stroke:#4fd6c4;stroke-width:2.2"/>
      <text x="136" y="80" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect class="skl-pop f-cal" x="160" y="86" width="12" height="18"/>
      <rect class="skl-pop f-cal" x="176" y="70" width="12" height="34"/>
      <rect class="skl-pop f-cal" x="192" y="58" width="12" height="46"/>
      <text x="182" y="118" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">metrics q</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_aggregate: {
    tip: "Per-model seed runs collapse to a mean and an error bar, separating seed noise from architecture effect.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="40" y1="116" x2="200" y2="116"/>
      <circle class="skl-pop f-cal" cx="94" cy="66" r="3" style="opacity:.7"/>
      <circle class="skl-pop f-cal" cx="122" cy="56" r="3" style="opacity:.7"/>
      <circle class="skl-pop f-cal" cx="112" cy="82" r="3" style="opacity:.7"/>
      <line class="skl-draw c-cal" x1="108" y1="46" x2="108" y2="92"/>
      <line class="skl-draw c-cal" x1="100" y1="46" x2="116" y2="46"/>
      <line class="skl-draw c-cal" x1="100" y1="92" x2="116" y2="92"/>
      <circle class="sk-live skl-pop f-cal" cx="108" cy="68" r="4.5"/>
      <text x="108" y="132" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">mean &#177; std</text>`; },
    anim: FlowSketches.pulse,
  },

  bench_leaderboard: {
    tip: "Headline metrics min-max to [0,1] and average into a composite Score; models rank, best on top.",
    build(svg) { svg.innerHTML = `
      <rect class="sk-live skl-pop f-fin" x="40" y="34" width="152" height="18" rx="2"/>
      <rect class="skl-pop f-cal" x="40" y="60" width="118" height="18" rx="2" style="opacity:.85"/>
      <rect class="skl-pop f-cal" x="40" y="86" width="90" height="18" rx="2" style="opacity:.7"/>
      <rect class="skl-pop f-cal" x="40" y="112" width="62" height="18" rx="2" style="opacity:.55"/>
      <text x="32" y="47" text-anchor="end" style="fill:#7e8aa0;font-size:7px">1</text>
      <text x="32" y="73" text-anchor="end" style="fill:#7e8aa0;font-size:7px">2</text>
      <text x="32" y="99" text-anchor="end" style="fill:#7e8aa0;font-size:7px">3</text>
      <text x="32" y="125" text-anchor="end" style="fill:#7e8aa0;font-size:7px">4</text>
      <text x="200" y="47" style="fill:#c4a3ff;font-size:8px">Score</text>`; },
    anim: FlowSketches.pulse,
  },

  cv_partition: {
    tip: "The fold azimuth window is cut into K equal contiguous blocks; the last block absorbs the remainder.",
    build(svg) {
      let b = "";
      for (let i = 0; i < 6; i++) b += `<rect x="${26 + i * 31}" y="52" width="29" height="46" class="skl-pop f-mid" style="opacity:${0.4 + 0.12 * (i % 2)}"/>`;
      svg.innerHTML = `<text x="120" y="40" text-anchor="middle" style="fill:#6ea8ff;font-size:8px">azimuth window [az0, az1)</text>${b}<line class="skl-axis" x1="26" y1="108" x2="212" y2="108"/><text x="26" y="122" style="fill:#7e8aa0;font-size:7px">az0 = 1000</text><text x="212" y="122" text-anchor="end" style="fill:#7e8aa0;font-size:7px">az1 = 16000</text>`;
    },
    anim: null,
  },

  cv_guard: {
    tip: "Interior boundaries erode by margin = g/2 on each side, opening a guard gap so no patch straddles two folds.",
    build(svg) { svg.innerHTML = `
      <rect x="24" y="44" width="80" height="60" class="skl-pop f-mid" style="opacity:.6"/>
      <rect x="136" y="44" width="80" height="60" class="skl-pop f-mid" style="opacity:.6"/>
      <rect x="104" y="44" width="32" height="60" class="skl-pop f-faint" style="opacity:.35"/>
      <line class="skl-dash c-faint" x1="120" y1="36" x2="120" y2="112"/>
      <text x="64" y="78" text-anchor="middle" style="fill:#0b1014;font-size:8px">B_k</text>
      <text x="176" y="78" text-anchor="middle" style="fill:#0b1014;font-size:8px">B_k+1</text>
      <text x="120" y="128" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">guard g = 64</text>`; },
    anim: null,
  },

  cv_assign: {
    tip: "For fold k the test band is block k, val is the next block, and the rest merge into the training regions.",
    build(svg) {
      const roles = ["train", "train", "test", "val", "train", "train"];
      const cls = { train: "f-meas", test: "f-fin", val: "f-cal" };
      let b = "";
      roles.forEach((r, i) => { const live = (r === "test" || r === "val") ? " sk-live" : ""; b += `<rect class="skl-pop ${cls[r]}${live}" x="${28 + i * 31}" y="50" width="28" height="42"/>`; });
      svg.innerHTML = `${b}<text x="104" y="42" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">test</text><text x="135" y="42" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">val</text><text x="120" y="110" text-anchor="middle" style="fill:#6ea8ff;font-size:8px">train = merge(rest)</text>`;
    },
    anim: FlowSketches.pulse,
  },

  cv_units: {
    tip: "Each fold is replicated once per seed into fold_k_seedS run units, queued across the configured GPUs.",
    build(svg) {
      let g = "";
      for (let r = 0; r < 3; r++) { g += `<text x="30" y="${58 + r * 26}" style="fill:#6ea8ff;font-size:7px">fold_${r}</text>`; for (let c = 0; c < 3; c++) g += `<rect class="sk-live skl-pop f-cal" x="${76 + c * 40}" y="${46 + r * 26}" width="34" height="18" style="opacity:${0.45 + 0.16 * c}"/>`; }
      svg.innerHTML = `<text x="146" y="36" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">seed 0    seed 1    seed 2</text>${g}`;
    },
    anim: FlowSketches.pulse,
  },

  cv_train: {
    tip: "Each fold trains an independent model on its train/val regions; the best-epoch checkpoint and its val loss are kept.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="34" y1="28" x2="34" y2="116"/>
      <line class="skl-axis" x1="34" y1="116" x2="212" y2="116"/>
      <path class="skl-draw c-faint" d="M34 46 C82 98 142 108 206 112" style="fill:none;opacity:.45"/>
      <path class="skl-draw c-faint" d="M34 56 C82 102 142 110 206 114" style="fill:none;opacity:.45"/>
      <path class="skl-draw c-mid sk-live" d="M34 40 C82 92 142 105 206 109" style="fill:none"/>
      <circle class="sk-live skl-pop f-cal" cx="150" cy="104" r="3.4"/>
      <text x="150" y="96" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">L*_k</text>
      <text x="120" y="132" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">epoch</text>`; },
    anim: FlowSketches.pulse,
  },

  cv_infer: {
    tip: "Each trained fold is inferred on its held-out val and test bands into per-split metrics (AE folds skip this).",
    build(svg) { svg.innerHTML = `
      <rect x="26" y="42" width="58" height="26" class="skl-pop f-cal" style="opacity:.8"/>
      <text x="55" y="59" text-anchor="middle" style="fill:#0b1014;font-size:8px">val</text>
      <rect x="26" y="86" width="58" height="26" class="skl-pop f-fin" style="opacity:.8"/>
      <text x="55" y="103" text-anchor="middle" style="fill:#0b1014;font-size:8px">test</text>
      <text x="100" y="82" style="fill:#7e8aa0;font-size:13px">&#8594;</text>
      <rect x="130" y="38" width="84" height="78" rx="3" class="skl-draw c-cal" style="fill:rgba(79,214,196,0.08)"/>
      <text x="172" y="58" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">MAE</text>
      <text x="172" y="74" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">RMSE</text>
      <text x="172" y="90" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">R2</text>
      <text x="172" y="106" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">SSIM</text>`; },
    anim: null,
  },

  cv_collect: {
    tip: "Seed replicas of a fold reduce to the across-seed mean and the within-fold seed standard deviation.",
    build(svg) { svg.innerHTML = `
      <circle class="skl-pop f-cal" cx="52" cy="50" r="3.4"/>
      <circle class="skl-pop f-cal" cx="52" cy="74" r="3.4"/>
      <circle class="skl-pop f-cal" cx="52" cy="98" r="3.4"/>
      <text x="52" y="122" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">seeds</text>
      <text x="102" y="80" style="fill:#7e8aa0;font-size:13px">&#8594;</text>
      <line class="skl-dash c-mid" x1="168" y1="50" x2="168" y2="98"/>
      <line class="skl-dash c-mid" x1="160" y1="50" x2="176" y2="50"/>
      <line class="skl-dash c-mid" x1="160" y1="98" x2="176" y2="98"/>
      <circle class="sk-live skl-pop f-mid" cx="168" cy="74" r="4.2"/>
      <text x="168" y="122" text-anchor="middle" style="fill:#f5b971;font-size:7px">mean, seed std</text>`; },
    anim: FlowSketches.pulse,
  },

  cv_aggregate: {
    tip: "Per-fold values aggregate to the cross-fold mean and sample std (ddof=1, only when >=2 folds contribute).",
    build(svg) {
      const ys = [64, 82, 70, 88, 72, 66, 84, 78];
      let d = "";
      ys.forEach((y, i) => { d += `<circle class="skl-pop f-cal" cx="${44 + i * 22}" cy="${y}" r="3"/>`; });
      svg.innerHTML = `<line class="skl-axis" x1="30" y1="116" x2="214" y2="116"/><rect class="sk-live skl-pop f-fin" x="34" y="62" width="176" height="28" style="opacity:.16"/><line class="skl-dash c-fin" x1="34" y1="76" x2="210" y2="76"/><text x="34" y="54" style="fill:#c4a3ff;font-size:7px">mean +/- std</text><text x="120" y="132" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">folds</text>${d}`;
    },
    anim: FlowSketches.pulse,
  },

  cv_report: {
    tip: "The fold plan, training summary and metric aggregates land in the report, the summary JSON and per-split comparisons.",
    build(svg) { svg.innerHTML = `
      <rect x="36" y="32" width="50" height="72" rx="3" class="skl-pop f-fin" style="opacity:.85"/>
      <line class="skl-axis" x1="44" y1="46" x2="78" y2="46"/>
      <line class="skl-axis" x1="44" y1="56" x2="78" y2="56"/>
      <line class="skl-axis" x1="44" y1="66" x2="78" y2="66"/>
      <text x="61" y="118" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">report.md</text>
      <rect x="98" y="42" width="46" height="62" rx="3" class="skl-pop f-cal" style="opacity:.8"/>
      <text x="121" y="118" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">summary.json</text>
      <rect x="158" y="50" width="42" height="54" rx="3" class="skl-pop f-mid" style="opacity:.7"/>
      <text x="179" y="118" text-anchor="middle" style="fill:#f5b971;font-size:7px">val / test</text>`; },
    anim: null,
  },

  spacelr: {
    tip: "Encoder, bottleneck, decoder and head LRs draw log-uniform over 1e-5 to 1e-2; dropout draws linearly over 0 to 0.5.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="210" y2="118"/>
      <text x="30" y="132" style="fill:#7e8aa0;font-size:7px">1e-5</text>
      <text x="190" y="132" text-anchor="end" style="fill:#7e8aa0;font-size:7px">1e-2</text>
      <circle class="sk-live skl-pop f-mid" cx="58" cy="118" r="4"/>
      <circle class="sk-live skl-pop f-mid" cx="112" cy="118" r="4"/>
      <circle class="sk-live skl-pop f-mid" cx="150" cy="118" r="4"/>
      <circle class="sk-live skl-pop f-mid" cx="192" cy="118" r="4"/>
      <line class="skl-axis" x1="30" y1="44" x2="210" y2="44"/>
      <text x="30" y="38" style="fill:#7e8aa0;font-size:7px">p_drop</text>
      <circle class="sk-live skl-pop f-cal" cx="96" cy="44" r="4"/>`; },
    anim: FlowSketches.pulse,
  },

  spacearch: {
    tip: "Five categorical knobs are sampled; the features index k decodes through a lookup to a list like [64,128,256,512].",
    build(svg) { svg.innerHTML = `
      <rect x="28" y="26" width="26" height="16" rx="3" class="skl-pop f-faint"/>
      <rect x="58" y="26" width="26" height="16" rx="3" class="skl-pop f-faint"/>
      <rect x="88" y="26" width="26" height="16" rx="3" class="skl-pop f-mid"/>
      <rect x="118" y="26" width="26" height="16" rx="3" class="skl-pop f-faint"/>
      <path class="skl-draw c-mid" d="M101 44 q24 16 58 16" style="fill:none"/>
      <rect x="150" y="50" width="62" height="18" rx="3" class="skl-pop f-cal"/>
      <text x="181" y="63" text-anchor="middle" style="fill:#0b1014;font-size:7px">[64,128,256,512]</text>
      <rect x="28" y="88" width="40" height="14" rx="3" class="skl-pop f-faint"/>
      <rect x="74" y="88" width="30" height="14" rx="3" class="skl-pop f-faint"/>
      <rect x="110" y="88" width="34" height="14" rx="3" class="skl-pop f-faint"/>
      <rect x="150" y="88" width="32" height="14" rx="3" class="skl-pop f-faint"/>`; },
    anim: null,
  },

  merge: {
    tip: "The 9-dim learning and 5-dim architecture blocks stack into one 14-D space that multivariate TPE samples jointly.",
    build(svg) { svg.innerHTML = `
      <rect x="34" y="42" width="46" height="66" rx="4" class="skl-pop f-mid" style="opacity:.85"/>
      <text x="57" y="34" text-anchor="middle" style="fill:#f5b971;font-size:8px">lr (9)</text>
      <text x="100" y="80" text-anchor="middle" style="fill:#7e8aa0;font-size:14px">+</text>
      <rect x="118" y="42" width="46" height="66" rx="4" class="skl-pop f-cal" style="opacity:.85"/>
      <text x="141" y="34" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">arch (5)</text>
      <text x="178" y="80" text-anchor="middle" style="fill:#7e8aa0;font-size:14px">=</text>
      <rect x="190" y="48" width="28" height="54" rx="4" class="skl-pop f-meas"/>
      <text x="204" y="116" text-anchor="middle" style="fill:#6ea8ff;font-size:8px">d=14</text>`; },
    anim: null,
  },

  tpesplit: {
    tip: "Trials split at the gamma quantile of loss into good and bad sets, each fit with its own KDE l(theta) and g(theta).",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="210" y2="118"/>
      <line class="skl-dash c-faint" x1="120" y1="26" x2="120" y2="122"/>
      <text x="110" y="22" style="fill:#7e8aa0;font-size:7px">y_g</text>
      <path class="skl-draw c-cal" d="M34 118 C70 118 86 40 110 40 C116 40 118 118 120 118 Z" style="fill:rgba(79,214,196,.18)"/>
      <path class="skl-draw c-mid" d="M120 118 C122 118 132 70 158 70 C190 70 196 118 206 118 Z" style="fill:rgba(245,185,113,.16)"/>
      <text x="64" y="60" style="fill:#4fd6c4;font-size:7px">l</text>
      <text x="160" y="92" style="fill:#f5b971;font-size:7px">g</text>`; },
    anim: null,
  },

  tpeacq: {
    tip: "TPE proposes the theta maximising l(theta)/g(theta), except the first n0 = 8 trials which sample uniformly.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="118" x2="210" y2="118"/>
      <path class="skl-draw c-cal" d="M34 110 C70 110 86 48 108 48 C120 48 124 110 130 110" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-mid" d="M40 110 C90 110 110 80 150 80 C188 80 196 110 206 110" style="fill:none;opacity:.5"/>
      <path class="skl-draw c-fin" d="M34 116 C66 116 80 36 104 30 C124 26 132 116 150 116 C170 116 206 116 206 116" style="fill:none"/>
      <line class="skl-dash c-fin" x1="104" y1="30" x2="104" y2="118"/>
      <circle class="sk-live skl-pop f-fin" cx="104" cy="30" r="5"/>
      <text x="60" y="26" style="fill:#c4a3ff;font-size:7px">l/g</text>`; },
    anim: FlowSketches.pulse,
  },

  liar: {
    tip: "Each pending trial gets the worst objective max f as a phantom value, so parallel workers avoid the same point.",
    build(svg) { svg.innerHTML = `
      <rect x="96" y="14" width="48" height="18" rx="4" class="skl-pop f-faint"/>
      <text x="120" y="27" text-anchor="middle" style="fill:#cfd8e8;font-size:7px">study</text>
      <rect x="28" y="74" width="36" height="22" rx="4" class="skl-pop f-faint"/>
      <rect x="84" y="74" width="36" height="22" rx="4" class="skl-pop f-faint"/>
      <rect x="140" y="74" width="36" height="22" rx="4" class="skl-pop f-faint"/>
      <line class="skl-axis" x1="120" y1="32" x2="46" y2="74" style="opacity:.4"/>
      <line class="skl-axis" x1="120" y1="32" x2="102" y2="74" style="opacity:.4"/>
      <line class="skl-axis" x1="120" y1="32" x2="158" y2="74" style="opacity:.4"/>
      <circle cx="46" cy="116" r="6" class="skl-pop f-mid"/>
      <circle cx="102" cy="116" r="6" class="skl-pop f-mid"/>
      <circle cx="158" cy="116" r="6" class="skl-pop f-mid"/>
      <text x="120" y="138" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">phantom max f</text>`; },
    anim: null,
  },

  trialsetup: {
    tip: "The base config is deep-copied per trial, overridden with E = 30, patience = 8, seed = 42 + trial.number.",
    build(svg) { svg.innerHTML = `
      <rect x="30" y="50" width="56" height="50" rx="5" class="skl-pop f-faint"/>
      <text x="58" y="116" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">base cfg</text>
      <path class="skl-draw c-faint" d="M90 75 L128 75 M120 70 L128 75 L120 80" style="fill:none"/>
      <rect x="134" y="46" width="60" height="58" rx="5" class="skl-pop f-mid"/>
      <line class="skl-draw c-cal" x1="142" y1="60" x2="186" y2="60"/>
      <line class="skl-draw c-cal" x1="142" y1="72" x2="186" y2="72"/>
      <line class="skl-draw c-cal" x1="142" y1="84" x2="186" y2="84"/>
      <text x="164" y="118" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">E=30 pat=8</text>`; },
    anim: null,
  },

  trial: {
    tip: "A trial trains on the fixed split up to 30 epochs and returns f(theta), the minimum validation loss.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="120" x2="210" y2="120"/>
      <line class="skl-axis" x1="30" y1="24" x2="30" y2="120"/>
      <path class="skl-draw c-cal" d="M30 36 C60 70 78 92 104 100 C140 110 170 104 206 102" style="fill:none"/>
      <line class="skl-dash c-fin" x1="30" y1="102" x2="206" y2="102"/>
      <circle class="sk-live skl-pop f-cal" cx="158" cy="102" r="4"/>
      <text x="158" y="96" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">min L</text>`; },
    anim: FlowSketches.pulse,
  },

  prune: {
    tip: "A trial whose loss stays above the running median m at step t is pruned, once 8 trials complete and t >= 8.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="120" x2="210" y2="120"/>
      <line class="skl-dash c-cal" x1="30" y1="72" x2="210" y2="72"/>
      <text x="34" y="66" style="fill:#4fd6c4;font-size:7px">median m</text>
      <line class="skl-dash c-faint" x1="92" y1="24" x2="92" y2="120"/>
      <text x="68" y="20" style="fill:#7e8aa0;font-size:7px">t>=8</text>
      <path class="skl-draw c-mid" d="M30 40 C50 56 70 64 92 66 C104 67 110 66 116 64" style="fill:none"/>
      <line class="skl-draw c-mid" x1="118" y1="58" x2="130" y2="70" style="stroke-width:2"/>
      <line class="skl-draw c-mid" x1="130" y1="58" x2="118" y2="70" style="stroke-width:2"/>`; },
    anim: null,
  },

  best: {
    tip: "Remaining trials run in GPU chunks; after each, theta* is rewritten as argmin f, decoding the features index to channels.",
    build(svg) { svg.innerHTML = `
      <rect x="28" y="26" width="14" height="18" rx="2" class="skl-pop f-faint"/>
      <rect x="46" y="26" width="14" height="18" rx="2" class="skl-pop f-faint"/>
      <rect x="64" y="26" width="14" height="18" rx="2" class="skl-pop f-mid"/>
      <rect x="82" y="26" width="14" height="18" rx="2" class="skl-pop f-mid"/>
      <text x="120" y="40" style="fill:#7e8aa0;font-size:7px">n_rem of 100</text>
      <line class="skl-axis" x1="30" y1="118" x2="210" y2="118"/>
      <circle cx="52" cy="86" r="3" class="skl-pop f-cal" style="opacity:.5"/>
      <circle cx="86" cy="70" r="3" class="skl-pop f-cal" style="opacity:.5"/>
      <circle cx="118" cy="98" r="3" class="skl-pop f-cal" style="opacity:.5"/>
      <circle class="sk-live skl-pop f-fin" cx="150" cy="110" r="5"/>
      <circle cx="184" cy="82" r="3" class="skl-pop f-cal" style="opacity:.5"/>
      <text x="150" y="132" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">argmin f</text>`; },
    anim: FlowSketches.pulse,
  },

  feed_target: {
    tip: "The mode's adapter wires the real dataset and model; the benchmark drives a genuine forward/backward/AdamW step.",
    build(svg) { svg.innerHTML = `
      <rect x="30" y="44" width="20" height="16" class="skl-pop f-meas"/>
      <rect x="30" y="64" width="20" height="16" class="sk-live skl-pop f-meas"/>
      <rect x="30" y="84" width="20" height="16" class="skl-pop f-meas"/>
      <text x="40" y="118" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">dataset</text>
      <text x="64" y="78" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <path class="skl-draw c-faint" d="M92 52 L140 66 L140 96 L92 110 Z" style="fill:none"/>
      <text x="116" y="126" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">f_theta step</text>
      <path class="skl-dash c-mid" d="M140 70 C180 58 180 104 140 92" style="fill:none"/>
      <text x="184" y="66" style="fill:#f5b971;font-size:7px">back</text>
      <circle cx="152" cy="120" r="4" class="skl-pop f-cal"/>
      <text x="180" y="124" style="fill:#4fd6c4;font-size:7px">L(x)</text>`; },
    anim: FlowSketches.pulse,
  },

  feed_grid: {
    tip: "Every (batch, workers) pair is a spec; the sweep visits each, dropping worker counts above the core budget C.",
    build(svg) {
      let g = "";
      for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) {
        const x = 52 + c * 30, y = 26 + r * 22, hot = (r === 1 && c === 2);
        g += `<rect class="skl-pop ${hot ? "sk-live f-cal" : "f-mid"}" x="${x}" y="${y}" width="26" height="18" style="opacity:${hot ? 1 : 0.22};stroke:#f5b971;stroke-width:.7"/>`;
      }
      svg.innerHTML = `${g}
        <text x="36" y="68" text-anchor="middle" transform="rotate(-90 36 68)" style="fill:#6ea8ff;font-size:7px">batch b</text>
        <text x="127" y="134" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">workers w</text>`;
    },
    anim: FlowSketches.pulse,
  },

  feed_loader: {
    tip: "With the GPU idle, 60 timed batches after 8 warm-up give the pure data-pipeline throughput R_load.",
    build(svg) { svg.innerHTML = `
      <rect x="28" y="58" width="18" height="30" class="sk-live skl-pop f-meas"/>
      <rect x="50" y="58" width="18" height="30" class="sk-live skl-pop f-meas" style="opacity:.75"/>
      <rect x="72" y="58" width="18" height="30" class="sk-live skl-pop f-meas" style="opacity:.5"/>
      <text x="108" y="78" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect x="134" y="52" width="74" height="42" rx="3" class="skl-draw c-cal" style="fill:rgba(79,214,196,0.1)"/>
      <text x="171" y="77" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">R_load</text>
      <text x="118" y="116" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">GPU idle (loader only)</text>`; },
    anim: FlowSketches.pulse,
  },

  feed_ceiling: {
    tip: "One batch is reused 60 times through the real train step; with zero data cost this is the GPU compute ceiling.",
    build(svg) { svg.innerHTML = `
      <rect x="34" y="60" width="22" height="30" class="skl-pop f-meas"/>
      <text x="45" y="106" text-anchor="middle" style="fill:#6ea8ff;font-size:7px">one x0</text>
      <path class="sk-live skl-dash c-mid" d="M58 66 C88 40 88 108 58 84" style="fill:none"/>
      <path class="skl-draw c-faint" d="M98 56 L138 68 L138 92 L98 104 Z" style="fill:none"/>
      <text x="118" y="120" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">f_theta step</text>
      <line class="skl-axis" x1="158" y1="104" x2="158" y2="34"/>
      <rect x="168" y="40" width="20" height="64" class="skl-pop f-cal"/>
      <text x="188" y="120" text-anchor="middle" style="fill:#4fd6c4;font-size:8px">R_gpu</text>`; },
    anim: FlowSketches.pulse,
  },

  feed_e2e: {
    tip: "Each batch's fetch-wait t_d and compute t_c are timed apart; their split is the data-wait fraction w_d.",
    build(svg) { svg.innerHTML = `
      <text x="30" y="42" style="fill:#7e8aa0;font-size:7px">one step time</text>
      <rect x="40" y="56" width="46" height="30" class="sk-live skl-pop f-mid"/>
      <text x="63" y="102" text-anchor="middle" style="fill:#f5b971;font-size:7px">t_d wait</text>
      <rect x="86" y="56" width="118" height="30" class="skl-pop f-cal"/>
      <text x="145" y="102" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">t_c compute</text>
      <line class="skl-axis" x1="40" y1="90" x2="204" y2="90"/>
      <text x="122" y="128" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">w_d = t_d / (t_d + t_c)</text>`; },
    anim: FlowSketches.pulse,
  },

  feed_ratios: {
    tip: "Feed ratio phi = loader / ceiling (>= 1 means CPU can outpace GPU); efficiency eta = achieved / ceiling.",
    build(svg) { svg.innerHTML = `
      <line class="skl-axis" x1="30" y1="120" x2="214" y2="120"/>
      <line class="skl-dash c-faint" x1="30" y1="52" x2="214" y2="52"/>
      <text x="210" y="48" text-anchor="end" style="fill:#7e8aa0;font-size:7px">1.0</text>
      <rect x="70" y="72" width="34" height="48" class="skl-pop f-cal"/>
      <text x="87" y="134" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">phi</text>
      <rect x="134" y="80" width="34" height="40" class="skl-pop f-cal" style="opacity:.7"/>
      <text x="151" y="134" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">eta</text>`; },
    anim: null,
  },

  feed_saturate: {
    tip: "Configs with data-wait <= 0.05 or feed-ratio >= 1 are GPU-saturated; none qualifying flags the run CPU-bound.",
    build(svg) {
      const pts = [[54, 46, 0], [84, 66, 0], [110, 98, 1], [140, 106, 1], [168, 112, 1], [196, 80, 0]];
      let d = "";
      pts.forEach(p => { const sat = p[2] === 1; d += `<circle cx="${p[0]}" cy="${p[1]}" r="4" class="${sat ? "sk-live skl-pop f-cal" : "skl-pop f-faint"}" style="opacity:${sat ? 1 : 0.5}"/>`; });
      svg.innerHTML = `
        <line class="skl-axis" x1="34" y1="120" x2="214" y2="120"/>
        <line class="skl-axis" x1="34" y1="28" x2="34" y2="120"/>
        <line class="skl-dash c-mid" x1="34" y1="92" x2="214" y2="92"/>
        <text x="210" y="88" text-anchor="end" style="fill:#f5b971;font-size:7px">tau = 0.05</text>
        ${d}
        <text x="124" y="134" text-anchor="middle" style="fill:#7e8aa0;font-size:7px">workers</text>
        <text x="24" y="40" style="fill:#7e8aa0;font-size:7px">w_d</text>`;
    },
    anim: FlowSketches.pulse,
  },

  feed_recommend: {
    tip: "Within the saturated pool the highest end-to-end throughput wins; ties break to fewer workers, then smaller batch.",
    build(svg) {
      const hs = [34, 52, 68, 60, 40];
      let b = "";
      hs.forEach((h, i) => { const x = 52 + i * 30, win = (i === 2); b += `<rect class="skl-pop ${win ? "sk-live f-fin" : "f-faint"}" x="${x}" y="${118 - h}" width="22" height="${h}" style="opacity:${win ? 1 : 0.45}"/>`; });
      svg.innerHTML = `<line class="skl-axis" x1="40" y1="118" x2="210" y2="118"/>${b}
        <circle cx="123" cy="42" r="4" class="sk-live skl-pop f-fin"/>
        <text x="120" y="134" text-anchor="middle" style="fill:#c4a3ff;font-size:7px">max R_e2e -> l*</text>`;
    },
    anim: FlowSketches.pulse,
  },

  feed_refine: {
    tip: "Batch and workers fixed, prefetch {2,4,8,16} x pin on/off is swept; the fastest cell tunes the transfer path.",
    build(svg) {
      let g = "";
      for (let r = 0; r < 2; r++) for (let c = 0; c < 4; c++) {
        const x = 66 + c * 30, y = 44 + r * 30, best = (r === 0 && c === 2);
        g += `<rect class="skl-pop ${best ? "sk-live f-cal" : "f-mid"}" x="${x}" y="${y}" width="26" height="26" style="opacity:${best ? 1 : 0.3}"/>`;
      }
      svg.innerHTML = `${g}
        <text x="128" y="30" text-anchor="middle" style="fill:#f5b971;font-size:7px">prefetch {2,4,8,16}</text>
        <text x="46" y="60" text-anchor="middle" transform="rotate(-90 46 60)" style="fill:#7e8aa0;font-size:6px">pin 1</text>
        <text x="46" y="90" text-anchor="middle" transform="rotate(-90 46 90)" style="fill:#7e8aa0;font-size:6px">pin 0</text>
        <text x="128" y="112" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">best (p*, pin*)</text>`;
    },
    anim: FlowSketches.pulse,
  },

  feed_final: {
    tip: "Batch and workers come from the recommendation; refine overrides prefetch and pin, else defaults 4 / on.",
    build(svg) { svg.innerHTML = `
      <rect x="60" y="30" width="120" height="92" rx="5" class="skl-draw c-fin" style="fill:rgba(196,163,255,0.08)"/>
      <text x="120" y="46" text-anchor="middle" style="fill:#c4a3ff;font-size:8px">final loader</text>
      <line class="skl-axis" x1="70" y1="54" x2="170" y2="54" style="opacity:.4"/>
      <text x="76" y="70" style="fill:#6ea8ff;font-size:7px">batch b*</text>
      <text x="76" y="84" style="fill:#6ea8ff;font-size:7px">workers w*</text>
      <text x="76" y="98" style="fill:#4fd6c4;font-size:7px">prefetch p*</text>
      <text x="76" y="112" style="fill:#4fd6c4;font-size:7px">pin*, persist</text>`; },
    anim: null,
  },

  feed_report: {
    tip: "results.json plus four figures: throughput-vs-batch, wait-vs-workers, util-vs-throughput, feed-ratio-vs-workers.",
    build(svg) { svg.innerHTML = `
      <rect x="28" y="40" width="54" height="70" rx="3" class="skl-pop f-fin" style="opacity:.85"/>
      <text x="55" y="80" text-anchor="middle" style="fill:#0b1014;font-size:8px">.json</text>
      <text x="94" y="80" style="fill:#7e8aa0;font-size:12px">&#8594;</text>
      <rect x="120" y="40" width="42" height="30" rx="2" class="skl-pop f-cal" style="opacity:.5"/>
      <rect x="168" y="40" width="42" height="30" rx="2" class="skl-pop f-cal" style="opacity:.5"/>
      <rect x="120" y="78" width="42" height="30" rx="2" class="skl-pop f-cal" style="opacity:.5"/>
      <rect x="168" y="78" width="42" height="30" rx="2" class="skl-pop f-cal" style="opacity:.5"/>
      <text x="165" y="124" text-anchor="middle" style="fill:#4fd6c4;font-size:7px">4 figures</text>`; },
    anim: null,
  },

};
}

window.FlowSketches = FlowSketches;
