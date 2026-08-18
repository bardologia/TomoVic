"""Public surface of the Gaussian parameter-extraction stage."""

from configuration.param_extraction                 import ExtractionConfig
from pipelines.processing.param_extraction.metrics  import FittingMetricsCalculator, KSelectionDiagnostics, ContrastEstimator
from pipelines.processing.param_extraction.io       import ExtractionMetadataManager, ParameterIO
from pipelines.processing.param_extraction.pipeline import ParameterExtractor, ParamExtractionPipeline
from pipelines.processing.param_extraction.plots    import FittingResultPlotter

__all__ = [
    "ExtractionConfig",
    "ExtractionMetadataManager",
    "FittingMetricsCalculator",
    "FittingResultPlotter",
    "KSelectionDiagnostics",
    "ParameterExtractor",
    "ParameterIO",
    "ParamExtractionPipeline",
    "ContrastEstimator",
]
