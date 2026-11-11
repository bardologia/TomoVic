"""Qt 5.15's QImage writers for the image files of pyqtgraph's ImageExporter.

TomoVis exported views with pyqtgraph's ImageExporter, which renders into an
ARGB32 ``QImage`` and calls ``QImage.save``; QImageWriter then picks the
writer from the file extension. The browser renders the same image and sends
it as PNG. This module writes it as Qt 5.15.15 (the original's Qt) did:

- ``QtPixels``     : qGray, premultiply and unpremultiply, and the Floyd-Steinberg mono conversion of ``dither_to_Mono``.
- ``QtSmoothScale``: ``qSmoothScaleImage``, the Imlib2 area-sampling scaler behind ``QImage.scaled(..., SmoothTransformation)``.
- ``QtImageWriter``: one writer per extension QImageWriter offered (bmp, cur, icns, ico, jpeg, jpg, pbm, pgm, png, ppm, tif, tiff, wbmp, webp, xbm, xpm).

Arrays are ``(height, width, 4)`` uint8 in R, G, B, A order; Qt applies the
same arithmetic to every channel, so the channel order does not change any
result.
"""

from __future__ import annotations

import io
import re
import struct
from pathlib import Path

import numpy as np
from PIL import Image


class QtPixels:
    """Pixel arithmetic of Qt 5.15 (qrgb.h, qimage_conversions.cpp).

    Attributes:
        INV_PREMUL_FACTOR : qt_inv_premul_factor, 0x00ff00ff // alpha for alpha 1..255 (index 0 unused).
    """

    INV_PREMUL_FACTOR = np.array([0] + [0x00FF00FF // alpha for alpha in range(1, 256)], dtype=np.int64)

    @staticmethod
    def gray(rgba: np.ndarray) -> np.ndarray:
        """qGray(r, g, b) = (11 r + 16 g + 5 b) / 32 of the stored (unpremultiplied) colour, alpha ignored.

        Args:
            rgba : (H, W, 4) uint8 image.

        Returns:
            (H, W) int64 gray levels 0..255.
        """

        channels = rgba.astype(np.int64)
        return (channels[..., 0] * 11 + channels[..., 1] * 16 + channels[..., 2] * 5) // 32

    @staticmethod
    def premultiply(rgba: np.ndarray) -> np.ndarray:
        """qPremultiply: c' = (c a + ((c a) >> 8) + 0x80) >> 8 per colour channel.

        Args:
            rgba : (H, W, 4) uint8 unpremultiplied image.

        Returns:
            (H, W, 4) uint8 premultiplied image.
        """

        channels = rgba.astype(np.int64)
        alpha    = channels[..., 3:4]
        product  = channels[..., :3] * alpha
        colour   = (product + ((product >> 8) & 0xFF) + 0x80) >> 8
        return np.concatenate([colour, alpha], axis=-1).astype(np.uint8)

    @classmethod
    def unpremultiply(cls, rgba: np.ndarray) -> np.ndarray:
        """qUnpremultiply: alpha 255 and 0 short-cut, otherwise (c * qt_inv_premul_factor[a] + 0x8000) >> 16.

        Args:
            rgba : (H, W, 4) uint8 premultiplied image.

        Returns:
            (H, W, 4) uint8 unpremultiplied image; fully transparent pixels become 0.
        """

        channels = rgba.astype(np.int64)
        alpha    = channels[..., 3]
        colour   = (channels[..., :3] * cls.INV_PREMUL_FACTOR[alpha][..., None] + 0x8000) >> 16
        colour   = np.where((alpha == 255)[..., None], channels[..., :3], colour)
        out      = np.concatenate([colour, alpha[..., None]], axis=-1)
        out[alpha == 0] = 0
        return out.astype(np.uint8)

    @staticmethod
    def monoBits(rgba: np.ndarray) -> np.ndarray:
        """Converts to Format_Mono as dither_to_Mono does with Qt's default DiffuseDither.

        Gray levels are qGray of the stored colour; a level below 128 becomes
        a black (1) pixel and the error spreads 7/16 right, 5/16 below, 3/16
        below left and the rest below right, each rounded as Qt rounds it.

        Args:
            rgba : (H, W, 4) uint8 image.

        Returns:
            (H, W) uint8 array of 0 (white, colour index 0) and 1 (black, colour index 1).
        """

        height, width = rgba.shape[:2]
        levels        = QtPixels.gray(rgba).tolist()
        bits          = np.zeros((height, width), dtype=np.uint8)
        line2         = list(levels[0])

        for y in range(height):
            line1         = line2
            not_last_line = y < height - 1
            if not_last_line:
                line2 = list(levels[y + 1])
            row = bits[y]
            for x in range(1, width + 1):
                value = line1[x - 1]
                if value < 128:
                    err        = value
                    row[x - 1] = 1
                else:
                    err = value - 255
                e7 = ((err * 7) + 8) >> 4
                e5 = ((err * 5) + 8) >> 4
                e3 = ((err * 3) + 8) >> 4
                e1 = err - (e7 + e5 + e3)
                if x < width:
                    line1[x] += e7
                if not_last_line:
                    line2[x - 1] += e5
                    if x > 1:
                        line2[x - 2] += e3
                    if x < width:
                        line2[x] += e1
        return bits

    @staticmethod
    def packBits(bits: np.ndarray, lsb: bool = False, bytes_per_line: int | None = None, pad_value: int = 0) -> np.ndarray:
        """Packs 0/1 pixels into scan lines as Format_Mono (MSB first) or Format_MonoLSB stores them.

        Args:
            bits           : (H, W) array of 0 and 1.
            lsb            : Least significant bit first (Format_MonoLSB).
            bytes_per_line : Scan line length in bytes; (W + 7) // 8 when None.
            pad_value      : Value of the bits past the last pixel of a line.

        Returns:
            (H, bytes_per_line) uint8 scan lines.
        """

        height, width  = bits.shape
        bytes_per_line = bytes_per_line or (width + 7) // 8
        padded         = np.full((height, bytes_per_line * 8), pad_value, dtype=np.uint8)
        padded[:, :width] = bits
        return np.packbits(padded, axis=1, bitorder="little" if lsb else "big")


class QtSmoothScale:
    """qSmoothScaleImage of Qt 5.15 (qimagescale.cpp with the SSE4.1 kernels used on x86).

    The image is premultiplied first, as QImage.smoothScaled converts an
    ARGB32 image to ARGB32_Premultiplied, and the result stays premultiplied.
    """

    @staticmethod
    def points(s: int, d: int) -> list[int]:
        """qimageCalcXPoints / qimageCalcYPoints: the first source index of every output index."""

        up  = d >= s
        val = (0x8000 * s // d - 0x8000) if up else 0
        inc = (s << 16) // d
        out = []
        for _ in range(d):
            out.append(max(0, val >> 16))
            val += inc
        return out

    @staticmethod
    def apoints(s: int, d: int, up: bool) -> list[int]:
        """qimageCalcApoints: 8-bit interpolation fractions when scaling up, (Cp << 16) | first weight when scaling down."""

        out = []
        inc = (s << 16) // d
        if up:
            val = 0x8000 * s // d - 0x8000
            for _ in range(d):
                pos = val >> 16
                out.append(0 if pos < 0 or pos >= s - 1 else (val >> 8) - ((val >> 8) & 0xFFFFFF00))
                val += inc
        else:
            val = 0
            cp  = ((d << 14) + s - 1) // s
            for _ in range(d):
                ap = ((0x10000 - (val & 0xFFFF)) * cp) >> 16
                out.append(ap | (cp << 16))
                val += inc
        return out

    @staticmethod
    def weights(points: list[int], apoints: list[int], s: int) -> tuple[np.ndarray, np.ndarray]:
        """Source indices and integer weights of qt_qimageScaleAARGBA_helper along one shrinking axis.

        Args:
            points  : First source index per output index.
            apoints : (C << 16) | first weight per output index.
            s       : Source length.

        Returns:
            (indices, weights), both (d, K) int64; the weights of a row sum to 1 << 14 and unused slots weigh 0.

        Raises:
            ValueError : If a weight would fall past the end of the axis, where Qt reads outside the line.
        """

        rows = []
        for start, packed in zip(points, apoints):
            step  = packed >> 16
            first = packed & 0xFFFF
            row   = [(start, first)]
            index = start
            j     = (1 << 14) - first
            while j > step:
                index += 1
                row.append((index, step))
                j -= step
            row.append((index + 1, j))
            rows.append(row)

        width   = max(len(row) for row in rows)
        indices = np.zeros((len(rows), width), dtype=np.int64)
        weights = np.zeros((len(rows), width), dtype=np.int64)
        for i, row in enumerate(rows):
            for k, (index, weight) in enumerate(row):
                indices[i, k] = index
                weights[i, k] = weight
        if (indices[weights > 0] >= s).any():
            raise ValueError("smooth scale weights run past the source")
        return indices, weights

    @staticmethod
    def sumAlong(values: np.ndarray, indices: np.ndarray, weights: np.ndarray, axis: int) -> np.ndarray:
        """Weighted sums of source lines along one axis.

        Args:
            values  : (H, W, 4) int64 pixels.
            indices : (d, K) source indices per output index.
            weights : (d, K) weights.
            axis    : 0 to sum rows, 1 to sum columns.

        Returns:
            int64 array with the axis replaced by d.
        """

        total = 0
        for k in range(indices.shape[1]):
            taken = np.take(values, indices[:, k], axis=axis)
            shape = [1, 1, 1]
            shape[axis] = indices.shape[0]
            total = total + taken * weights[:, k].reshape(shape)
        return total

    @staticmethod
    def lerp(a: np.ndarray, b: np.ndarray, fraction: np.ndarray) -> np.ndarray:
        """(a (256 - f) + b f) >> 8, Qt's INTERPOLATE_PIXEL_256 per channel."""

        return (a * (256 - fraction) + b * fraction) >> 8

    def scale(self, rgba: np.ndarray, dw: int, dh: int) -> np.ndarray:
        """Scales an unpremultiplied ARGB32 image with QImage.smoothScaled.

        Args:
            rgba : (H, W, 4) uint8 unpremultiplied image.
            dw   : Output width.
            dh   : Output height.

        Returns:
            (dh, dw, 4) uint8 premultiplied image.
        """

        source = QtPixels.premultiply(rgba).astype(np.int64)
        sh, sw = source.shape[:2]
        x_up   = dw >= sw
        y_up   = dh >= sh

        xpoints  = self.points(sw, dw)
        ypoints  = self.points(sh, dh)
        xapoints = self.apoints(sw, dw, x_up)
        yapoints = self.apoints(sh, dh, y_up)

        if x_up and y_up:
            out = self.upXY(source, xpoints, ypoints, xapoints, yapoints)
        elif x_up:
            column = self.sumAlong(source, *self.weights(ypoints, yapoints, sh), axis=0)
            out    = self.upAxis(column, xpoints, xapoints, axis=1) >> 14
        elif y_up:
            row = self.sumAlong(source, *self.weights(xpoints, xapoints, sw), axis=1)
            out = self.upAxis(row, ypoints, yapoints, axis=0) >> 14
        else:
            row = self.sumAlong(source, *self.weights(xpoints, xapoints, sw), axis=1) >> 4
            out = self.sumAlong(row, *self.weights(ypoints, yapoints, sh), axis=0) >> 24
        return np.clip(out, 0, 255).astype(np.uint8)

    def upAxis(self, values: np.ndarray, points: list[int], apoints: list[int], axis: int) -> np.ndarray:
        """Interpolates between neighbours along a growing axis where the fraction is non-zero.

        Args:
            values  : (H, W, 4) int64 sums along the other axis.
            points  : First source index per output index.
            apoints : 8-bit fractions per output index.
            axis    : 0 for rows, 1 for columns.

        Returns:
            int64 array with the axis resampled to len(points).
        """

        first    = np.asarray(points)
        fraction = np.asarray(apoints, dtype=np.int64)
        second   = np.minimum(first + 1, values.shape[axis] - 1)
        a        = np.take(values, first, axis=axis)
        b        = np.take(values, second, axis=axis)
        shape    = [1, 1, 1]
        shape[axis] = len(points)
        fraction = fraction.reshape(shape)
        return np.where(fraction > 0, self.lerp(a, b, fraction), a)

    def upXY(self, source: np.ndarray, xpoints: list[int], ypoints: list[int], xapoints: list[int], yapoints: list[int]) -> np.ndarray:
        """qt_qimageScaleAARGBA_up_xy: bilinear between four pixels, vertical first, then horizontal."""

        sh, sw = source.shape[:2]
        x0     = np.asarray(xpoints)
        y0     = np.asarray(ypoints)
        x1     = np.minimum(x0 + 1, sw - 1)
        y1     = np.minimum(y0 + 1, sh - 1)
        xap    = np.asarray(xapoints, dtype=np.int64)[None, :, None]
        yap    = np.asarray(yapoints, dtype=np.int64)[:, None, None]

        top_left     = source[y0][:, x0]
        top_right    = source[y0][:, x1]
        bottom_left  = source[y1][:, x0]
        bottom_right = source[y1][:, x1]

        left  = self.lerp(top_left, bottom_left, yap)
        right = self.lerp(top_right, bottom_right, yap)
        both  = self.lerp(left, right, xap)
        down  = self.lerp(top_left, bottom_left, yap)
        side  = self.lerp(top_left, top_right, xap)
        return np.where(yap > 0, np.where(xap > 0, both, down), np.where(xap > 0, side, top_left))

    def scaledSize(self, width: int, height: int, target_w: int, target_h: int, keep_aspect: bool) -> tuple[int, int]:
        """QImage::scaled's output size: QSize::scaled, at least 1x1, then transformed()'s int(scale * size + 0.9999).

        Args:
            width       : Source width.
            height      : Source height.
            target_w    : Requested width.
            target_h    : Requested height.
            keep_aspect : Qt::KeepAspectRatio instead of Qt::IgnoreAspectRatio.

        Returns:
            (width, height) of the scaled image.
        """

        new_w, new_h = target_w, target_h
        if keep_aspect and width and height:
            rw = target_h * width // height
            if rw <= target_w:
                new_w, new_h = rw, target_h
            else:
                new_w, new_h = target_w, target_w * height // width
        new_w = max(new_w, 1)
        new_h = max(new_h, 1)
        if (new_w, new_h) == (width, height):
            return width, height
        return int(abs(new_w / width) * width + 0.9999), int(abs(new_h / height) * height + 0.9999)


class QtImageWriter:
    """QImage.save for the image formats QImageWriter offered TomoVis.

    Attributes:
        DPI         : Logical dots per inch stored in the files, Qt's default on a Linux desktop without Xft.dpi.
        FORMATS     : Extensions written, as QImageWriter.supportedImageFormats() listed them in the original.
        XPM_CODE    : Characters of xpm_color_name.
        scaler      : Smooth scaler for the ICO and ICNS writers.
    """

    DPI      = 96
    FORMATS  = ("bmp", "cur", "icns", "ico", "jpeg", "jpg", "pbm", "pgm", "png", "ppm", "tif", "tiff", "wbmp", "webp", "xbm", "xpm")
    XPM_CODE = ".#abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def __init__(self) -> None:
        """Creates the writer."""

        self.scaler = QtSmoothScale()

    def rgba(self, png: bytes) -> np.ndarray:
        """Decodes the browser's PNG to a (H, W, 4) uint8 RGBA array."""

        with Image.open(io.BytesIO(png)) as image:
            return np.asarray(image.convert("RGBA")).copy()

    def encode(self, suffix: str, png: bytes) -> bytes | None:
        """Encodes the image for an extension as QImageWriter does.

        Args:
            suffix : Lower-case extension without the dot.
            png    : PNG bytes rendered by the browser.

        Returns:
            The file contents, or None where QImage.save returns False (unknown extension, too many XPM colours, empty ICNS).
        """

        if suffix not in self.FORMATS:
            return None
        if suffix == "png":
            return png
        rgba = self.rgba(png)
        if suffix in ("pbm", "pgm"):
            return self.netpbm(rgba, suffix)
        if suffix == "xbm":
            return self.xbm(rgba)
        if suffix == "xpm":
            return self.xpm(rgba)
        if suffix == "wbmp":
            return self.wbmp(rgba)
        if suffix in ("ico", "cur"):
            return self.ico(rgba)
        if suffix == "icns":
            return self.icns(rgba)
        return self.pillow(rgba, suffix)

    def pillow(self, rgba: np.ndarray, suffix: str) -> bytes:
        """bmp, jpeg, ppm, tiff and webp through Pillow with Qt's settings.

        BMP and PPM keep the colour and drop alpha (24-bit BMP, P6), JPEG uses
        quality 75 and drops alpha, TIFF keeps RGBA uncompressed, WebP is lossy
        at quality 75 with alpha quality 75; BMP, JPEG and TIFF store the
        logical DPI.
        """

        image  = Image.fromarray(rgba, "RGBA")
        buffer = io.BytesIO()
        if suffix == "bmp":
            image.convert("RGB").save(buffer, format="BMP", dpi=(self.DPI, self.DPI))
        elif suffix in ("jpg", "jpeg"):
            image.convert("RGB").save(buffer, format="JPEG", quality=75, dpi=(self.DPI, self.DPI))
        elif suffix == "ppm":
            image.convert("RGB").save(buffer, format="PPM")
        elif suffix in ("tif", "tiff"):
            image.save(buffer, format="TIFF", dpi=(self.DPI, self.DPI))
        else:
            image.save(buffer, format="WEBP", quality=75, alpha_quality=75)
        return buffer.getvalue()

    def netpbm(self, rgba: np.ndarray, suffix: str) -> bytes:
        """write_pbm_image for pbm (Format_Mono, P4) and pgm (Format_Grayscale8, P5)."""

        height, width = rgba.shape[:2]
        if suffix == "pbm":
            body = QtPixels.packBits(QtPixels.monoBits(rgba)).tobytes()
            return f"P4\n{width} {height}\n".encode() + body
        body = QtPixels.gray(rgba).astype(np.uint8).tobytes()
        return f"P5\n{width} {height}\n255\n".encode() + body

    def xbm(self, rgba: np.ndarray) -> bytes:
        """write_xbm_image: Format_MonoLSB bytes as C hex, 15 per line; QImage.save passes no name, so the identifiers are _width, _height and _bits."""

        height, width = rgba.shape[:2]
        lines         = QtPixels.packBits(QtPixels.monoBits(rgba), lsb=True)
        text          = [f"#define _width {width}\n", f"#define _height {height}\n", "static char _bits[] = {\n "]
        chunk         = ""
        count         = 0
        bytes_per_row = lines.shape[1]
        for y in range(height):
            for i in range(bytes_per_row):
                chunk += f"0x{lines[y, i]:02x}"
                if i < bytes_per_row - 1 or y < height - 1:
                    chunk += ","
                    count += 1
                    if count > 14:
                        chunk += "\n "
                        text.append(chunk)
                        chunk = ""
                        count = 0
        text.append(chunk + " };\n")
        return "".join(text).encode()

    def xpmName(self, cpp: int, index: int) -> str:
        """xpm_color_name, including Qt's swap of the codes for index 0 and 64 * 44 + 21."""

        code  = self.XPM_CODE
        chars = ["", "", "", ""]
        if cpp > 1:
            if cpp > 2:
                if cpp > 3:
                    chars[3] = code[index % 64]
                    index //= 64
                chars[2] = code[index % 64]
                index //= 64
            if index == 0:
                index = 64 * 44 + 21
            elif index == 64 * 44 + 21:
                index = 0
            chars[1] = code[index % 64]
            index //= 64
        chars[0] = code[index]
        return "".join(chars)

    def xpm(self, rgba: np.ndarray) -> bytes | None:
        """write_xpm_image of an ARGB32 image: palette in QRgb order, "None" for alpha 0, codes in first-use order; the name is "dummy"."""

        height, width = rgba.shape[:2]
        channels      = rgba.astype(np.uint32)
        keys          = (channels[..., 3] << 24) | (channels[..., 0] << 16) | (channels[..., 1] << 8) | channels[..., 2]
        flat          = keys.ravel()
        unique, first = np.unique(flat, return_index=True)
        order         = np.argsort(first, kind="stable")
        index_of      = np.empty(len(unique), dtype=np.int64)
        index_of[order] = np.arange(len(unique))
        ncolors       = len(unique)

        cpp = 1
        k   = 64
        while ncolors > k:
            cpp += 1
            if cpp > 4:
                return None
            k *= 64

        names = [self.xpmName(cpp, int(i)) for i in range(ncolors)]
        lines = ["/* XPM */", "static char *dummy[]={", f'"{width} {height} {ncolors} {cpp}"']
        for key, index in zip(unique.tolist(), index_of.tolist()):
            if (key >> 24) == 0:
                lines[-1] += ","
                lines.append(f'"{names[index]} c None"')
            else:
                lines[-1] += ","
                lines.append(f'"{names[index]} c #{(key >> 16) & 0xFF:02x}{(key >> 8) & 0xFF:02x}{key & 0xFF:02x}"')

        pixel_index = index_of[np.searchsorted(unique, flat)].reshape(height, width)
        for y in range(height):
            lines[-1] += ","
            lines.append('"' + "".join(names[i] for i in pixel_index[y].tolist()) + '"')
        return ("\n".join(lines) + "};\n").encode()

    def wbmp(self, rgba: np.ndarray) -> bytes:
        """WBMPReader::writeImage: Format_Mono inverted to WBMP's 1 = white (padding bits included), type 0, multi-byte width and height."""

        height, width = rgba.shape[:2]
        lines         = QtPixels.packBits(QtPixels.monoBits(rgba)) ^ 0xFF
        return bytes([0, 0]) + self.multiByte(width) + self.multiByte(height) + lines.tobytes()

    def multiByte(self, number: int) -> bytes:
        """writeMultiByteInt: 7 bits per byte, most significant group first, continuation bit 0x80.

        Qt stacks the groups in an integer and writes its bytes until the
        rest is zero, so a zero lowest group (a multiple of 128) is dropped.
        """

        tmp     = number & 0x7F
        number >>= 7
        while number:
            group   = number & 0x7F
            number >>= 7
            tmp     = (tmp << 8) | (group | 0x80)
        out = []
        while tmp:
            out.append(tmp & 0xFF)
            tmp >>= 8
        return bytes(out)

    def ico(self, rgba: np.ndarray) -> bytes:
        """ICOReader::write: one 32-bit BMP entry with an AND mask; images over 256 px are smooth-scaled to fit 256x256 keeping the aspect ratio.

        Qt writes the same ICO data for a .cur file. QImage::fill sets only
        the (W + 7) / 8 bytes of each mask line, so Qt's alignment bytes after
        them hold whatever the allocation held; they are written as zeros.
        """

        height, width = rgba.shape[:2]
        image         = rgba
        if width > 256 or height > 256:
            dw, dh = self.scaler.scaledSize(width, height, 256, 256, keep_aspect=True)
            image  = QtPixels.unpremultiply(self.scaler.scale(rgba, dw, dh))
        height, width = image.shape[:2]

        bpl_bmp     = ((width * 32 + 31) // 32) * 4
        mask_bpl    = ((width + 31) // 32) * 4
        transparent = (image[..., 3] == 0).astype(np.uint8)
        filled      = QtPixels.packBits(transparent, pad_value=1)
        mask        = np.zeros((height, mask_bpl), dtype=np.uint8)
        mask[:, :filled.shape[1]] = filled
        pixels      = image[..., [2, 1, 0, 3]][::-1].tobytes()
        data        = pixels + mask[::-1].tobytes()
        size        = 40 + bpl_bmp * height + mask_bpl * height

        header = struct.pack("<HHH", 0, 1, 1)
        entry  = struct.pack("<BBBBHHII", width if width < 256 else 0, height if height < 256 else 0, 0, 0, 1, 32, size, 6 + 16)
        info   = struct.pack("<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0, size - 40, 0, 0, 0, 0)
        return header + entry + info + data

    def icns(self, rgba: np.ndarray) -> bytes | None:
        """QICNSHandler::write: one PNG icon, smooth-scaled to a square power of two between 16 and 1024 when needed."""

        height, width = rgba.shape[:2]
        min_size      = min(width, height)
        if min_size == 0:
            return None
        size = 16 if min_size < 16 else min_size
        pow2 = 0
        while pow2 < 10 and (size >> 1):
            size >>= 1
            pow2 += 1
        new_size = 1 << pow2
        old_size = 16 if min_size < 16 else min_size
        image    = rgba
        if new_size != old_size or max(width, height) != min_size:
            dw, dh = self.scaler.scaledSize(width, height, new_size, new_size, keep_aspect=False)
            image  = QtPixels.unpremultiply(self.scaler.scale(rgba, dw, dh))

        buffer = io.BytesIO()
        Image.fromarray(image, "RGBA").save(buffer, format="PNG", dpi=(self.DPI, self.DPI))
        png    = buffer.getvalue()
        ostype = (b"icp" + str(pow2).encode()) if pow2 < 7 else (b"ic" + f"{pow2:02d}".encode())
        entry  = 8 + len(png)
        toc    = 16
        return b"icns" + struct.pack(">I", 8 + toc + entry) + b"TOC " + struct.pack(">I", toc) + ostype + struct.pack(">I", entry) + ostype + struct.pack(">I", entry) + png

    def write(self, target: Path, png: bytes) -> bool:
        """Writes the image to ``target`` in the format its extension names, as QImage.save.

        Args:
            target : Absolute path whose directory exists.
            png    : PNG bytes rendered by the browser.

        Returns:
            False where QImage.save returned False (unknown or missing extension, unwritable image), True after writing.
        """

        suffix = target.suffix.lower().lstrip(".")
        if not re.fullmatch(r"[a-z]+", suffix or "-"):
            return False
        data = self.encode(suffix, png)
        if data is None:
            return False
        target.write_bytes(data)
        return True
