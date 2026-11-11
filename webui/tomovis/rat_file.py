"""Read path of DLR STEtools' RAT file format, copied from TomoVis's Visualizer/ste_io.py.

TomoVis imports ``.rat`` files through ``ste_io.rrat``. The header
structures and the read path of ``RatFile`` are copied here with only the
fixes numpy 2 needs (crash fix E-006): ``np.int`` becomes ``int``, one-element
arrays are converted with ``int(x[0])``, ``tostring`` becomes ``tobytes`` and
``np.product`` becomes ``np.prod``. Write paths, memory-mapped reads, ENVI
headers, HDF helpers and the XML classes are not reachable from TomoVis and
are not copied. The terminal prints of the original go to the console log.
"""

from __future__ import annotations

import ctypes
import mmap
import warnings

import numpy as np

from web_logger import WebLogger


class RatHeaderRat(ctypes.Structure):
    """The 100-byte RAT block of a RAT 2.0 header: magic, version, shape, data type."""

    _pack_   = 1
    _fields_ = [("magiclong", ctypes.c_int),
                ("version", ctypes.c_float),
                ("ndim", ctypes.c_int),
                ("nchannel", ctypes.c_int),
                ("idl_shape", ctypes.c_int * 8),
                ("var", ctypes.c_int),
                ("sub", ctypes.c_int * 2),
                ("rattype", ctypes.c_int),
                ("reserved", ctypes.c_int * 9)]

    def __init__(self, **kwargs) -> None:
        """Fills the block as STEtools does: magic 844382546, version 2.0, shape reversed to IDL order.

        Args:
            kwargs : shape, ndim, nchannel, var, rattype, sub, as RatHeaderRat accepts them.
        """

        self.magiclong = 844382546
        self.version   = 2.0
        if 'shape' in kwargs:
            self.idl_shape = (ctypes.c_int * 8)(*kwargs['shape'][::-1])
            if 'ndim' in kwargs:
                self.ndim = ctypes.c_int(kwargs['ndim'])
            else:
                self.ndim = ctypes.c_int(len(kwargs['shape']))
            if 'nchannel' in kwargs:
                self.nchannel = ctypes.c_int(kwargs['nchannel'])
            else:
                if len(kwargs['shape']) <= 2:
                    self.nchannel = ctypes.c_int(1)
                else:
                    self.nchannel = ctypes.c_int(int(np.prod(kwargs['shape'][2::])))
        if 'var' in kwargs:
            self.var = ctypes.c_int(kwargs['var'])
        if 'rattype' in kwargs:
            self.rattype = ctypes.c_int(kwargs['rattype'])
        if 'sub' in kwargs:
            self.sub = (ctypes.c_int * 2)(*kwargs['sub'])
        else:
            self.sub = (ctypes.c_int * 2)(1, 1)


class RatHeaderInfo(ctypes.Structure):
    """The 100-character description line of a RAT header."""

    _pack_   = 1
    _fields_ = [("info", ctypes.c_char * 100)]


class RatHeaderGeo(ctypes.Structure):
    """The geocoding block of a RAT header."""

    _pack_   = 1
    _fields_ = [("projection", ctypes.c_short),
                ("ps_east", ctypes.c_double),
                ("ps_north", ctypes.c_double),
                ("min_east", ctypes.c_double),
                ("min_north", ctypes.c_double),
                ("zone", ctypes.c_short),
                ("hemisphere", ctypes.c_short),
                ("long0scl", ctypes.c_double),
                ("max_axis_ell", ctypes.c_double),
                ("min_axis_ell", ctypes.c_double),
                ("dshift_tx", ctypes.c_double),
                ("dshift_ty", ctypes.c_double),
                ("dshift_tz", ctypes.c_double),
                ("dshift_rx", ctypes.c_double),
                ("dshift_ry", ctypes.c_double),
                ("dshift_rz", ctypes.c_double),
                ("dshift_scl", ctypes.c_double),
                ("dshift_info", ctypes.c_char * 64),
                ("reserved", ctypes.c_byte * 18)]


class RatHeaderEmpty(ctypes.Structure):
    """A reserved 100-byte block of a RAT header."""

    _pack_   = 1
    _fields_ = [("reserved", ctypes.c_int * 25)]


class RatHeader(ctypes.Structure):
    """The 1000-byte RAT 2.0 header."""

    _pack_   = 1
    _fields_ = [("Rat", RatHeaderRat),
                ("Info", RatHeaderInfo),
                ("Geo", RatHeaderGeo),
                ("Stat", RatHeaderEmpty),
                ("Reserved1", RatHeaderEmpty),
                ("Reserved2", RatHeaderEmpty),
                ("Reserved3", RatHeaderEmpty),
                ("Reserved4", RatHeaderEmpty),
                ("Reserved5", RatHeaderEmpty)]

    def __init__(self, **kwargs) -> None:
        """Builds the RAT block from the keyword arguments.

        Args:
            kwargs : Passed to RatHeaderRat.
        """

        self.Rat = RatHeaderRat(**kwargs)


class RatFile:
    """A RAT 1.0 or 2.0 file opened for reading (STEtools RatFile, read path only).

    Attributes:
        logger   : Console logger receiving the original's terminal error lines.
        filename : Path of the file.
        Header   : Parsed RatHeader.
        shape    : Numpy shape of the stored array.
        version  : 1.0 or 2.0.
        xdrflag  : 1 when a RAT 1.0 file is big-endian (XDR), else 0.
        ndim     : Number of dimensions.
        dtype    : Numpy dtype of the stored array.
        info     : Header description text.
        var      : IDL data type code.
        nchannel : Channel count from the header.
        exists   : Whether the header could be read.
    """

    DTYPE_DICT = {1: 'uint8',
                  2: 'int16',
                  3: 'int32',
                  4: 'float32',
                  5: 'float64',
                  6: 'complex64',
                  9: 'complex128',
                  12: 'uint16',
                  13: 'uint32',
                  14: 'int64',
                  15: 'uint64'}

    def __init__(self, filename: str, logger: WebLogger) -> None:
        """Reads the header when the file exists, as RatFile.__init__.

        Args:
            filename : Path of the RAT file.
            logger   : Console logger.

        Raises:
            ValueError : If the file is neither RAT 1.0 nor RAT 2.0 (decision D-3 reports it as an import error).
        """

        self.logger   = logger
        self.filename = filename
        self.Header   = RatHeader()
        self.shape    = ()
        try:
            self.version, self.xdrflag = self.get_version()
            self.read_header()
            self.shape    = self._get_shape()
            self.ndim     = len(self.shape)
            self.dtype    = self._get_dtype()
            self.info     = self.Header.Info.info.decode()
            self.var      = int(self.Header.Rat.var)
            self.nchannel = int(self.Header.Rat.nchannel)
            self.exists   = True
        except IOError:
            self.exists = False

    def _ioerror(self, msg: str) -> None:
        """Logs the original's red terminal line and raises IOError.

        Raises:
            IOError : Always, with ``msg``.
        """

        self.logger.error("TomoVis: " + msg)
        raise IOError(msg)

    def get_version(self) -> tuple:
        """Returns (version, xdrflag) from the file's first bytes.

        Raises:
            ValueError : If the file is neither format; the original printed "ERROR: format not recognised!" and returned (False, False).
        """

        Header    = RatHeader()
        magiclong = Header.Rat.magiclong
        magicreal = 0

        with open(self.filename, 'rb') as lun:
            magicreal = np.fromfile(file=lun, dtype="i4", count=1)
        if magicreal != magiclong:
            with open(self.filename, 'rb') as lun:
                ndim = np.fromfile(file=lun, dtype="<i4", count=1)
            xdrflag = 0
            if ndim < 0 or ndim > 9:
                ndim    = ndim.byteswap()
                xdrflag = 1
            if ndim < 0 or ndim > 9:
                self.logger.error("TomoVis: ERROR: format not recognised!")
                raise ValueError("format not recognised")
            version = 1.0
        else:
            with open(self.filename, 'rb') as lun:
                lun.seek(4)
                version = np.fromfile(file=lun, dtype="float32", count=1)[0]
            xdrflag = 0

        return version, xdrflag

    def read_header(self) -> None:
        """Reads the RAT 2.0 header block, or rebuilds one from a RAT 1.0 header."""

        self.version = self.get_version()[0]
        if self.version == 2.0:
            with open(self.filename, 'rb') as lun:
                lun.readinto(self.Header)

        elif self.version == 1.0:
            warnings.warn('Old RAT v1.0 format!')
            if self.xdrflag == 1:
                data_type = '>i4'
                offset    = 4 * 4
            else:
                data_type = '<i4'
                offset    = 3 * 4

            with open(self.filename, 'rb') as lun:
                ndim    = int(np.fromfile(file=lun, dtype=data_type, count=1)[0])
                shape   = np.fromfile(file=lun, dtype=data_type, count=ndim).tolist()
                shape   = shape[::-1]
                var     = int(np.fromfile(file=lun, dtype=data_type, count=1)[0])
                rattype = int(np.fromfile(file=lun, dtype=data_type, count=1)[0])
                lun.seek(offset, 1)
                info    = np.fromfile(file=lun, dtype="B", count=80).tobytes().rstrip()

            self.Header           = RatHeader(shape=shape, ndim=ndim, var=var, rattype=rattype)
            self.Header.Info.info = info

        else:
            self._ioerror('ERROR: RAT version not supported')

        self.dtype = self._get_dtype()

    def _get_dtype(self) -> np.dtype:
        """Returns the numpy dtype of the header's IDL type code."""

        if self.Header.Rat.var not in self.DTYPE_DICT:
            self._ioerror('The data type is either not specified or not supported!')
        return np.dtype(self.DTYPE_DICT[self.Header.Rat.var])

    def _get_shape(self) -> tuple:
        """Returns the numpy shape: the IDL shape without zeros, reversed."""

        shape = np.ctypeslib.as_array(self.Header.Rat.idl_shape)
        shape = shape[shape != 0]
        return tuple(shape[::-1])

    def read(self) -> np.ndarray:
        """Reads the whole array into a fresh in-memory copy.

        Returns:
            The stored array with the header's shape and dtype, byteswapped for XDR files.

        Raises:
            IOError : If the header could not be read or the version is unsupported.
        """

        if self.exists == False:
            self._ioerror('ERROR: The file is not found')

        block       = np.zeros(2 * len(self.shape), dtype=int)
        block[1::2] = self.shape

        ind = tuple(map(lambda x, y: slice(x, y, None), block[::2], block[1::2]))

        if self.version == 2.0:
            offset = 1000
        elif self.version == 1.0:
            offset = int(104 + 4 * self.Header.Rat.ndim + 4 * self.xdrflag)
        else:
            self._ioerror('ERROR: RAT version not supported')

        with open(self.filename, 'rb') as lun:
            mm = mmap.mmap(lun.fileno(), length=0, access=mmap.ACCESS_READ)

            arr = (np.ndarray.__new__(np.ndarray, self.shape, dtype=self.dtype, buffer=mm, offset=offset)[ind])
            if self.xdrflag == 1:
                arr = arr.byteswap()
        arr_new    = np.zeros(shape=arr.shape, dtype=arr.dtype)
        arr_new[:] = arr
        return arr_new


class RatReader:
    """STEtools' ``rrat`` entry point.

    Attributes:
        logger : Console logger passed to every RatFile.
    """

    def __init__(self, logger: WebLogger) -> None:
        """Stores the logger."""

        self.logger = logger

    def rrat(self, filename: str) -> np.ndarray:
        """Reads an entire RAT file.

        Args:
            filename : Path of the RAT file.

        Returns:
            The stored array.
        """

        rat_file = RatFile(filename, self.logger)
        return rat_file.read()
