"use strict";

class MathJaxTypesetter {
  static MAX_ATTEMPTS = 250;
  static POLL_MS      = 120;
  static readyPromise = null;

  static ready() {
    if (MathJaxTypesetter.readyPromise) return MathJaxTypesetter.readyPromise;

    MathJaxTypesetter.readyPromise = new Promise((resolve, reject) => {
      let attempts = 0;
      const check  = () => {
        if (window.MathJax && window.MathJax.tex2svgPromise) {
          resolve();
          return;
        }

        attempts += 1;
        if (attempts >= MathJaxTypesetter.MAX_ATTEMPTS) {
          reject(new Error(`MathJax did not load after ${attempts} polls of ${MathJaxTypesetter.POLL_MS} ms`));
          return;
        }

        setTimeout(check, MathJaxTypesetter.POLL_MS);
      };
      check();
    }).then(() => {
      if (!document.getElementById("MJX-SVG-styles")) document.head.appendChild(window.MathJax.svgStylesheet());
    });

    return MathJaxTypesetter.readyPromise;
  }

  static render(el, tex, display, source) {
    el.textContent = tex;

    return MathJaxTypesetter.ready()
      .then(() => window.MathJax.tex2svgPromise(source || tex, { display: !!display }))
      .then((node) => {
        el.textContent = "";
        el.appendChild(node);
        return node;
      })
      .catch((err) => {
        el.textContent = tex;
        console.error(`MathJax typeset failed for "${tex}": ${err.message}`);
        return null;
      });
  }
}

window.MathJaxTypesetter = MathJaxTypesetter;
