"use strict";

class ZipArchive {
  static SIGNATURE_LOCAL   = 0x04034b50;
  static SIGNATURE_CENTRAL = 0x02014b50;
  static SIGNATURE_END     = 0x06054b50;
  static LOCAL_BYTES       = 30;
  static CENTRAL_BYTES     = 46;
  static END_BYTES         = 22;
  static VERSION           = 20;
  static FLAG_UTF8         = 0x0800;
  static METHOD_STORE      = 0;
  static CRC_TABLE         = null;

  constructor() {
    this.parts   = [];
    this.entries = [];
    this.offset  = 0;
    this.stamp   = ZipArchive.dosStamp(new Date());
  }

  static dosStamp(when) {
    return {
      time : (when.getHours() << 11) | (when.getMinutes() << 5) | (when.getSeconds() >> 1),
      date : ((when.getFullYear() - 1980) << 9) | ((when.getMonth() + 1) << 5) | when.getDate(),
    };
  }

  static crcTable() {
    if (ZipArchive.CRC_TABLE) return ZipArchive.CRC_TABLE;

    const table = new Uint32Array(256);

    for (let index = 0; index < 256; index += 1) {
      let value = index;
      for (let bit = 0; bit < 8; bit += 1) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
      table[index] = value >>> 0;
    }

    ZipArchive.CRC_TABLE = table;
    return table;
  }

  static crc32(bytes) {
    const table = ZipArchive.crcTable();
    let value = 0xffffffff;

    for (let index = 0; index < bytes.length; index += 1) value = table[(value ^ bytes[index]) & 0xff] ^ (value >>> 8);

    return (value ^ 0xffffffff) >>> 0;
  }

  add(name, bytes) {
    const label = new TextEncoder().encode(name);
    const crc   = ZipArchive.crc32(bytes);
    const head  = new DataView(new ArrayBuffer(ZipArchive.LOCAL_BYTES));

    head.setUint32(0,  ZipArchive.SIGNATURE_LOCAL, true);
    head.setUint16(4,  ZipArchive.VERSION,         true);
    head.setUint16(6,  ZipArchive.FLAG_UTF8,       true);
    head.setUint16(8,  ZipArchive.METHOD_STORE,    true);
    head.setUint16(10, this.stamp.time,            true);
    head.setUint16(12, this.stamp.date,            true);
    head.setUint32(14, crc,                        true);
    head.setUint32(18, bytes.length,               true);
    head.setUint32(22, bytes.length,               true);
    head.setUint16(26, label.length,               true);
    head.setUint16(28, 0,                          true);

    this.entries.push({ label, crc, size: bytes.length, offset: this.offset });
    this.parts.push(new Uint8Array(head.buffer), label, bytes);
    this.offset += ZipArchive.LOCAL_BYTES + label.length + bytes.length;
  }

  _directory() {
    const blocks = [];

    this.entries.forEach((entry) => {
      const head = new DataView(new ArrayBuffer(ZipArchive.CENTRAL_BYTES));

      head.setUint32(0,  ZipArchive.SIGNATURE_CENTRAL, true);
      head.setUint16(4,  ZipArchive.VERSION,           true);
      head.setUint16(6,  ZipArchive.VERSION,           true);
      head.setUint16(8,  ZipArchive.FLAG_UTF8,         true);
      head.setUint16(10, ZipArchive.METHOD_STORE,      true);
      head.setUint16(12, this.stamp.time,              true);
      head.setUint16(14, this.stamp.date,              true);
      head.setUint32(16, entry.crc,                    true);
      head.setUint32(20, entry.size,                   true);
      head.setUint32(24, entry.size,                   true);
      head.setUint16(28, entry.label.length,           true);
      head.setUint16(30, 0,                            true);
      head.setUint16(32, 0,                            true);
      head.setUint16(34, 0,                            true);
      head.setUint16(36, 0,                            true);
      head.setUint32(38, 0,                            true);
      head.setUint32(42, entry.offset,                 true);

      blocks.push(new Uint8Array(head.buffer), entry.label);
    });

    return blocks;
  }

  blob() {
    const directory = this._directory();
    const size      = directory.reduce((total, part) => total + part.length, 0);
    const end       = new DataView(new ArrayBuffer(ZipArchive.END_BYTES));

    end.setUint32(0,  ZipArchive.SIGNATURE_END, true);
    end.setUint16(4,  0,                        true);
    end.setUint16(6,  0,                        true);
    end.setUint16(8,  this.entries.length,      true);
    end.setUint16(10, this.entries.length,      true);
    end.setUint32(12, size,                     true);
    end.setUint32(16, this.offset,              true);
    end.setUint16(20, 0,                        true);

    return new Blob([...this.parts, ...directory, new Uint8Array(end.buffer)], { type: "application/zip" });
  }
}


class FigureExport {
  static SLUG_MAX     = 72;
  static SVG_SCALE    = 2;
  static OPAQUE       = /^rgba?\((\s*\d+\s*,){2}\s*\d+\s*(,\s*(0?\.\d*[1-9]\d*|1(\.0*)?)\s*)?\)$/;
  static SVG_STYLES   = [
    "fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-dasharray",
    "stroke-linecap", "stroke-linejoin", "opacity", "font-family", "font-size", "font-weight",
    "font-style", "letter-spacing", "text-anchor", "dominant-baseline", "color",
  ];

  static slug(text, max) {
    const clean = String(text == null ? "" : text)
      .replace(/[‐-―−]/g, "-")
      .replace(/[·•]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/[^A-Za-z0-9._-]+/g, "_")
      .replace(/_+/g, "_")
      .replace(/^[_.-]+|[_.-]+$/g, "");
    return clean.slice(0, max || FigureExport.SLUG_MAX).replace(/[_.-]+$/g, "");
  }

  static download(name, source) {
    const url  = typeof source === "string" ? source : URL.createObjectURL(source);
    const link = document.createElement("a");

    link.href     = url;
    link.download = name;
    link.click();

    if (url !== source) setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  static backdrop(el) {
    let node = el;

    while (node && node.nodeType === 1) {
      const color = getComputedStyle(node).backgroundColor;
      if (FigureExport.OPAQUE.test(color)) return color;
      node = node.parentElement;
    }

    return "#ffffff";
  }

  static canvasBlob(canvas) {
    return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), "image/png"));
  }

  static flatten(canvas, background) {
    const flat = document.createElement("canvas");
    flat.width  = canvas.width;
    flat.height = canvas.height;

    const ctx = flat.getContext("2d");
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, flat.width, flat.height);
    ctx.drawImage(canvas, 0, 0);

    return flat;
  }

  static fromCanvas(canvas) {
    return FigureExport.canvasBlob(FigureExport.flatten(canvas, FigureExport.backdrop(canvas)));
  }

  static upscale(img) {
    const shown = img.getBoundingClientRect().width;
    if (!img.naturalWidth || !shown) return 1;
    return Math.max(1, Math.round(shown / img.naturalWidth));
  }

  static async fromImage(img) {
    const scale = FigureExport.upscale(img);

    if (scale === 1) {
      const response = await fetch(img.currentSrc || img.src);
      return await response.blob();
    }

    const canvas = document.createElement("canvas");
    canvas.width  = img.naturalWidth * scale;
    canvas.height = img.naturalHeight * scale;

    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    return await FigureExport.canvasBlob(canvas);
  }

  static inlineStyles(source, clone) {
    const originals = [source, ...source.querySelectorAll("*")];
    const copies    = [clone, ...clone.querySelectorAll("*")];

    originals.forEach((node, index) => {
      const copy = copies[index];
      if (!copy || !copy.style) return;

      const computed = getComputedStyle(node);
      FigureExport.SVG_STYLES.forEach((prop) => {
        const value = computed.getPropertyValue(prop);
        if (value) copy.style.setProperty(prop, value);
      });
    });
  }

  static rasterize(url, width, height, background) {
    return new Promise((resolve, reject) => {
      const image = new Image();

      image.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width  = width;
        canvas.height = height;

        const ctx = canvas.getContext("2d");
        ctx.fillStyle = background;
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(image, 0, 0, width, height);

        resolve(FigureExport.canvasBlob(canvas));
      };
      image.onerror = () => reject(new Error("the figure could not be rasterized"));
      image.src = url;
    });
  }

  static async fromSvg(svg) {
    const rect   = svg.getBoundingClientRect();
    const width  = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    const clone  = svg.cloneNode(true);

    FigureExport.inlineStyles(svg, clone);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", String(width));
    clone.setAttribute("height", String(height));

    const text = new XMLSerializer().serializeToString(clone);
    const url  = URL.createObjectURL(new Blob([text], { type: "image/svg+xml;charset=utf-8" }));
    const scale = FigureExport.SVG_SCALE;

    try {
      return await FigureExport.rasterize(url, width * scale, height * scale, FigureExport.backdrop(svg));
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  static async blobFor(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === "canvas") return await FigureExport.fromCanvas(el);
    if (tag === "img")    return await FigureExport.fromImage(el);
    if (tag === "svg")    return await FigureExport.fromSvg(el);
    return null;
  }

  static async saveElement(el, name) {
    const blob = await FigureExport.blobFor(el);
    if (!blob) return false;

    FigureExport.download(name, blob);
    return true;
  }

  static async saveCanvas(canvas, name) {
    const blob = await FigureExport.fromCanvas(canvas);
    if (blob) FigureExport.download(name, blob);
  }

  static async saveBitmap(bitmap, name) {
    const canvas = document.createElement("canvas");
    canvas.width  = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0);

    await FigureExport.saveCanvas(canvas, name);
  }

  static async saveZip(name, jobs) {
    const archive = new ZipArchive();
    let saved = 0;

    for (const job of jobs) {
      const blob = await FigureExport.blobFor(job.el).catch(() => null);
      if (!blob) continue;

      archive.add(job.name, new Uint8Array(await blob.arrayBuffer()));
      saved += 1;
    }

    if (saved) FigureExport.download(name, archive.blob());
    return saved;
  }
}


window.ZipArchive    = ZipArchive;
window.FigureExport  = FigureExport;
