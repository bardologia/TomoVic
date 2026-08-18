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


};
}

window.FlowSketches = FlowSketches;
