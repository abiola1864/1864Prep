"""Transform registry.

The AI mapping layer never manipulates data. Its whole output is a plan that
names transforms from this registry and supplies their parameters. Adding a new
cleaning rule means adding a Transform subclass and registering it here.
"""
from __future__ import annotations

from .auto_categorical import AutoCategoricalTransform
from .categorical import CategoryTransform, SLATransform, TicketSourceTransform
from .dates import DateISOTransform
from .geo import LGANCCTransform, LGANGTransform, StateNGTransform
from .identity import FixedLengthIdTransform, NINTransform
from .phone import PhoneNGTransform
from .providers import ProviderTransform, ProviderTypeTransform
from .resolve_tf import ResolveTransform
from .text import (BooleanTransform, EmailTransform, GenderTransform,
                    NameTransform, NumericTransform, TextNormaliseTransform,
                    UpperTransform)

REGISTRY = {
    # identity / contact (social-register use case)
    "nin": NINTransform,
    "fixed_id": FixedLengthIdTransform,
    "phone_ng": PhoneNGTransform,
    # geography (state map + LGA shared across use cases)
    "resolve": ResolveTransform,
    "auto_categorical": AutoCategoricalTransform,  # induce vocab then standardise    # robust fuzzy+phonetic resolver (DEFAULT approach)
    "state_ng": StateNGTransform,   # strict dictionary reproduction of the R script
    "lga_ncc": LGANCCTransform,      # faithful NCC 5-step LGA pipeline
    "lga_ng": LGANGTransform,        # reference/prefix matcher (register example)
    # dates
    "date_iso": DateISOTransform,
    # text
    "name": NameTransform,
    "upper": UpperTransform,
    "gender": GenderTransform,
    "email": EmailTransform,
    "boolean": BooleanTransform,
    "numeric": NumericTransform,
    "text_normalise": TextNormaliseTransform,
    # NCC complaints domain
    "provider": ProviderTransform,
    "provider_type": ProviderTypeTransform,
    "category": CategoryTransform,
    "ticket_source": TicketSourceTransform,
    "sla": SLATransform,
}


def get_transform(name: str, **params):
    if name not in REGISTRY:
        raise KeyError(f"Unknown transform '{name}'. Available: {sorted(REGISTRY)}")
    return REGISTRY[name](**params)


def list_transforms() -> list[str]:
    return sorted(REGISTRY)
