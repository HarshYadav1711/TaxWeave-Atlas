"""Typed errors for explicit failures (no silent recovery)."""


class TaxWeaveError(Exception):
    """Base error for explicit failures (no silent guessing)."""


class NotImplementedStageError(TaxWeaveError):
    """Boundary for features intentionally absent in the current project stage."""


class ConfigurationError(TaxWeaveError):
    """Missing or invalid reference pack / template configuration."""


class MappingResolutionError(TaxWeaveError):
    """A mapping key could not be resolved on the tax case."""


class ValidationError(TaxWeaveError):
    """Consistency or schema validation failed."""


class ReconciliationError(TaxWeaveError):
    """Reconciliation or cross-document numeric alignment failed."""


class RendererError(TaxWeaveError):
    """PDF rendering failed."""
