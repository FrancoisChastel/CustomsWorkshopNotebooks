# The legacy rules of months 1-18 (R1-R5) in plain words and in SQL

Lanes: red before yellow before green. Every yellow and red line was controlled; the random draw (R5) was controlled whatever its lane. Officer discretion escalated a further 1-3% of green lines by office. Two per cent of lane assignments were overridden by hand (override_flag).

| Rule | Plain words | Lane | SQL (features_lines) |
| --- | --- | --- | --- |
| R1 | The importer's first line is less than 12 months old | yellow | `new_importer = 1` |
| R2 | The declared value per kilo is below 70% of the reference price set in 2022 for the code (tariff.static_reference_2022, in USD/kg, origin-blind, never refreshed) | red | `value_per_kg / 25 < 0.7 * static_reference_2022` (join tariff on hs8) |
| R3 | Sensitive goods (chapters 22, 24, 85, 87 and the refined-sugar line) lodged at AIR2, LAND1 | yellow | `chapter IN ('22','24','85','87') OR hs6 = '170199') AND office IN ('AIR2', 'LAND1')` |
| R4 | A preference is claimed and the origin is MYS or IDN | yellow | `preference_claim = 'FTA' AND origin IN ('MYS', 'IDN')` |
| R5 | A random share of 10% drawn before R1-R4, stratified by office and regime, controlled in full | its own lane | `random_draw = 1` |

Controls: yellow = documentary (plus scanner at ports and airports, plus physical at land crossings); red = documentary + physical + a valuation query (plus scanner at ports); random draw = documentary + physical + a valuation query when the price is below the peer median (plus scanner at ports).

What the five rules cannot see: a reference price that no longer moves with the market (R2 decays on months 19-36), a scheme that owns its own peer group, and everything that is not a price, a chapter, an origin or a date.
