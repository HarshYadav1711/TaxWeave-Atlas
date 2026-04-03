class TaxWeaveError(Exception):
    """Base error for explicit failures (no silent guessing)."""


class ConfigurationError(TaxWeaveError):
    """Missing or invalid reference pack / template configuration."""


class MappingResolutionError(TaxWeaveError):
    """A mapping key could not be resolved on the tax case."""


class ValidationError(TaxWeaveError):
    """Consistency or schema validation failed."""


class RendererError(TaxWeaveError):
    """PDF rendering failed."""
