"use strict";
const fs   = require("fs");
const os   = require("os");
const path = require("path");

class ChromiumResolver {

  CACHE_ROOT = path.join(os.homedir(), ".cache", "ms-playwright");
  EXE_RELS   = ["chrome-headless-shell-linux64/chrome-headless-shell", "chrome-linux/chrome"];
  BUILD_NUM  = /(\d+)$/;

  buildNumber(dir) {
    const match = this.BUILD_NUM.exec(dir);
    return match ? Number(match[1]) : 0;
  }

  candidates() {
    if (!fs.existsSync(this.CACHE_ROOT))
      throw new Error("no playwright cache at " + this.CACHE_ROOT + " (run 'npx playwright-core install chromium', or set PW_CHROMIUM)");

    return fs.readdirSync(this.CACHE_ROOT)
             .filter(d => d.startsWith("chromium"))
             .sort((a, b) => this.buildNumber(b) - this.buildNumber(a));
  }

  resolve() {
    if (process.env.PW_CHROMIUM) return process.env.PW_CHROMIUM;

    for (const d of this.candidates()) {
      for (const rel of this.EXE_RELS) {
        const exe = path.join(this.CACHE_ROOT, d, rel);
        if (fs.existsSync(exe)) return exe;
      }
    }
    throw new Error("no chromium found under " + this.CACHE_ROOT + " (set PW_CHROMIUM)");
  }
}

module.exports = { ChromiumResolver };
