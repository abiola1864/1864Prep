# Region packs — Nigeria is one config, not the engine

The engine is **generic**. It cleans any country's data by leaning on
established, locale-aware libraries:

| Concern | Library | Generic behaviour |
|---------|---------|-------------------|
| Phones | `phonenumbers` (Google libphonenumber) | validates/normalises for every country; region is a parameter |
| Dates | `dateparser` | parses many formats/locales; day/month order from the region |
| Numbers & currency | `price-parser` | `₦`, `$`, `€`, thousands separators, comma-vs-dot decimals |
| Text / encoding | `ftfy`, `charset-normalizer` | repair mojibake, sniff encoding |
| Email | `email-validator` | RFC validation + normalisation, offline |
| Names / values | `rapidfuzz`, `jellyfish` | fuzzy + phonetic matching, language-agnostic |
| Ingestion | `pandas`, `openpyxl`, `pdfplumber` | CSV/Excel/JSON/PDF |

Anything country-specific lives in a **Region** (`regions/base.py`): the default
phone region, date order, currency symbols, and optional reference lists
(states, places, LGAs). Nigeria (`NG`) is one such pack; `GENERIC` assumes
nothing.

```python
import regions
regions.set_active_region("ng")     # or register your own
ref = regions.load_reference()      # -> gazetteers / place_index / gazetteer_refs
```

## Add a country in a few lines

```python
from regions.base import Region
import regions
regions.register_region(Region(
    key="ke", name="Kenya", phone_region="KE", date_order="DMY",
    currency_symbols=("KSh", "KES"),
    states_ref="reference/ke_counties.json",   # optional
))
regions.set_active_region("ke")
```

The same transforms then clean Kenyan phones (`0712… -> +254…`), Kenyan dates,
and Kenyan money — no engine changes. Swapping the pack is the only difference.
