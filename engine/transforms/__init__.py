"""Transform registry.

The mapping layer never manipulates data. Its output is a plan that names
transforms from this registry and supplies their parameters. Adding a new
cleaning rule means adding a Transform subclass and registering it here.
"""
from __future__ import annotations

from .auto_categorical import AutoCategoricalTransform
from .dates import DateISOTransform
from .geo import LGANGTransform, StateNGTransform
from .identity import FixedLengthIdTransform, NINTransform
from .phone import PhoneNGTransform
from .resolve_tf import ResolveTransform
from .text import (BooleanTransform, EmailTransform, GenderTransform,
                   NameTransform, NumericTransform, TextCleanTransform,
                   TextNormaliseTransform, UpperTransform)

REGISTRY = {
    # identity / contact
    "nin": NINTransform,
    "fixed_id": FixedLengthIdTransform,
    "phone_ng": PhoneNGTransform,
    # standardisation
    "resolve": ResolveTransform,            # robust fuzzy+phonetic resolver (default)
    "auto_categorical": AutoCategoricalTransform,  # induce a vocabulary, then standardise
    "state_ng": StateNGTransform,           # match to the official states via a reference list
    "lga_ng": LGANGTransform,               # reference / prefix matcher for LGAs
    # dates
    "date_iso": DateISOTransform,
    # text / values
    "name": NameTransform,
    "upper": UpperTransform,
    "gender": GenderTransform,
    "email": EmailTransform,
    "boolean": BooleanTransform,
    "numeric": NumericTransform,
    "text_normalise": TextNormaliseTransform,
    "text_clean": TextCleanTransform,   # natural-language / free-text cleanup
}


def get_transform(name: str, **params):
    if name not in REGISTRY:
        raise KeyError(f"Unknown transform '{name}'. Available: {sorted(REGISTRY)}")
    return REGISTRY[name](**params)


def list_transforms() -> list[str]:
    return sorted(REGISTRY)
