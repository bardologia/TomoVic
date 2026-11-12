"""Dataset bridge between the TomoVis page and the TomoVic tools.

A file imported in TomoVis becomes a light run directory in the console's
workspace, so the Cube, Slices and launch pages read it like any preprocessing
run; a TomoVic run reaches TomoVis through a small FuSAR hd5 link file whose one
dataset is stored externally in the run's tomogram. One current dataset per
console is shared by every page, and the pieces a tool still needs (height
range, primary image, DEM, geometry and so on) can be added to an import.
"""
