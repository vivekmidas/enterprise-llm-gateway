from app.knowledge.transformers.base import BaseResponseTransformer, ResponseTransformerRegistry
from app.knowledge.transformers.default import DefaultResponseTransformer
from app.knowledge.transformers.legal import LegalResponseTransformer

# Register default transformers
ResponseTransformerRegistry.register("general", DefaultResponseTransformer())
ResponseTransformerRegistry.register("default", DefaultResponseTransformer())
ResponseTransformerRegistry.register("legal", LegalResponseTransformer())

__all__ = [
    "BaseResponseTransformer",
    "ResponseTransformerRegistry",
    "DefaultResponseTransformer",
    "LegalResponseTransformer",
]
