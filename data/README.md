# Data dictionary (DATASET-v3)

One generated world, seed 20261019, 1 October 2023 to 30 September 2026, home country HOM, LCU at a fixed 25 per USD. Real ISO codes for origins and partners, none a participating country. Every record is synthetic.

Calibration line: random draw finds something on 1 to 8 lines in a hundred; this set is enriched on the 20 exercise lines only.

`outcome` is filled only where a control took place; an uncontrolled line carries null, never 'no finding'. Months 1-18 carry the legacy lanes and their control results; months 19-36 carry no lanes and only the random draw with its results.

## Tables

| Table | What it is |
| --- | --- |
| `declarations_h1.csv` | Months 1-18: every line, the legacy lane, and the control outcome wherever a control took place. |
| `declarations_h2.csv` | Months 19-36: every line; no lanes; outcomes only on the random draw. |
| `features_lines.csv` | The precomputed signals and scores for every line of both halves (see Features). |
| `trader_features.csv` | One row per importer: value, lines, origins and exporters, price deviation, broker flagged share, tenure, amendment rate, exemption share, hit rate on months 1-18 where controlled, cluster. |
| `importers.csv` | The importer register as customs holds it (no latent attribute). |
| `brokers.csv` | Licensed brokers. |
| `exporters.csv` | Foreign sellers. |
| `consignees.csv` | Who receives the goods, and under whose importer code. |
| `tariff.csv` | The 400 HS8 lines: duty, unit, usual weight per unit, producers, CIF/FOB wedge, the 2022 static reference price of the legacy rule R2. |
| `offices.csv` | The 12 offices with their control capacity. |
| `fx_rates.csv` | Fixed rates per month. |
| `reference_prices.csv` | Median value per kg by code and origin over the 36 months. |
| `accepted_history.csv` | 2B valuation: every home-use line of months 34-36 that was not a random draw with a finding, as declared, with accepted_on. |
| `invoice_lines.csv` | 2B valuation: the five invoice lines of the exercise. |
| `valuation_neighbours.csv` | For every accepted line of months 34-36 and the five invoice lines (query_id): the 30 nearest accepted lines of the same heading and origin by description embedding, with similarity. |
| `mirror_trade.csv` | Partner exports (true FOB, from the world) against home imports (declared CIF) by partner, chapter and year, with the partner-side effects. |
| `regional_unit_values.csv` | Stylised regional statistics: eight goods, ten importing countries (A = home), two rulers. |
| `sector_regional.csv` | Stylised: ten chapters x ten countries, greyed under 70% weight coverage. |
| `monthly_importer_uv.csv` | Monthly value per kg of the 50 largest importers' main code, with the reference median. |
| `tax_registry.csv` | The tax administration's register (1,800 taxpayers). |
| `vat_returns.csv` | 24 monthly periods per registered taxpayer; filed = 0 rows carry blank amounts. |
| `importers_4b.csv` | The 25 importers of the 4B exercise. |
| `match_example_600.csv` | The 600 importers of the match example (importer_id only). |
| `licences.csv` | Relief licences of the exemption beneficiaries. |
| `warehouse_stock.csv` | Warehouse stock accounts by operator and month. |
| `transit.csv` | Transit movements. |
| `parcels.csv` | Low-value parcels by consignee and month. |
| `land_border_mirror.csv` | Imports at each land crossing against the neighbour's exports through it. |
| `corridor_importers.csv` | 2B sprint 2. Every importer of the plastics corridor (chapter 39 from the first partner), one row each: how much of what is left unexplained (the residual) it carries, its six fingerprints (new, broker, bunching, alternating, office, price: 1 when it fires) and its declared value month by month for the last twelve months. Ranked by its share of the residual. |
| `invoice_extract.csv` | 2B sprint 3. What a document reader pulled from each invoice: related party, royalty clause, discount, the delivery terms written on the invoice; each with how sure the reader is (0 to 1). It reads the paper; the declaration carries its own figures, and the two can disagree. |
| `valuation_neighbours_invoice.csv` | 2B sprint 3. For each of the five invoice lines, the 30 accepted lines whose description is most alike, with the price put on one basis (dollars, FOB), how alike they are (similarity, 0 to 1) and whether they pass the 0.85 floor. The range is read on the lines above the floor. |
| `pairs_4b.csv` | 4B sprint 1. The 25 importers against the tax register with the deck's recipe: how alike the name, the address and the director are (0 to 1), whether the phone matches, the combined confidence (name x 0.4 + address x 0.3 + director x 0.3, a missing field left out) and the band at the dial 0.90 / 0.70: link, review, no link. |
| `network_counts.csv` | 4B sprint 3. The four counts per importer: the consignees (every party clearing under its tax ID: the other names declaring under it, plus its consignee records), the addresses and the brokers behind them, and turnover declared over imports. The flag fires at 8 or more consignees, one address and turnover under 20%. |
| `rulebook_numbers.csv` | 1B sprint 1. The five old rules R1-R5 on each half of the data: share of traffic, hit rate (on the random draw for months 19-36), lift against the random draw, duty recovered per inspection, new to the book (flags no other rule raises), burden on compliant traders, the queue beyond a 5% budget, and the hit rate quarter by quarter. |
| `menu_1b.csv` | 1B sprint 2. Twenty-four starting rules on the fields the evaluator accepts, in plain words and as a condition, scored on months 1-18: share of traffic, hit rate on the controlled lines they flag, lift against the random draw of months 1-18, new to the book. A starting point, never an answer: the honest test comes after the lock. |
| `sample_1b.csv` | 1B sprint 2. 25,000 lines for the Excel Sample sheet: value per kilo, the typical value of the peers, the spread, the distance from normal (the z, log and linear), the peer level used, the five recipe columns; the deck's worked line is flagged (deck_example = 1). |
| `recipe_steps_1b.csv` | 1B sprint 2. Three or four settings of the one choice each recipe leaves open (recipes 2 to 5), as a condition, with their numbers on the random draw of months 1-18 only: share of traffic, random-draw lines flagged, findings, hit rate and lift against that draw. The months 19-36 test comes after the lock. |

## declarations_h1 / declarations_h2

| Field | Meaning |
| --- | --- |
| `line_id` | Line identifier (L + 7 digits); the key of every per-line table |
| `decl_id` | Declaration number (DCL + 7 digits) |
| `line_no` | Line number within the declaration |
| `decl_date` | Date the declaration was lodged |
| `month` | Year-month of the declaration |
| `period_month` | Month 1-36 of the window (1 = October 2023) |
| `office` | Customs office (see offices) |
| `regime` | home_use, home_use_exempt, warehouse_in, warehouse_out, transit, temporary_admission, re_export |
| `importer_id` | Customs' own importer code (IMP + 5 digits) |
| `importer_name_customs` | Importer name as keyed on the declaration (a trading name for about 10%) |
| `tin_customs` | Tax ID as customs holds it: blank for the informal importers, one character off for 6%, lent for a borrowed name |
| `address_customs` | Address as keyed |
| `phone_customs` | Phone as keyed |
| `consignee_id` | Who receives the goods (see consignees) |
| `broker_id` | Customs broker who lodged the line |
| `exporter_id` | Foreign seller (blank on the valuation cells) |
| `exporter_name` | Seller's name as declared |
| `exporter_country` | Seller's country |
| `origin` | Declared country of origin (ISO 3; never a participating country) |
| `consignment_country` | Country the goods were shipped from (a hub for some lines) |
| `hs8` | Declared tariff code (8 digits) |
| `hs6` | First six digits |
| `chapter` | First two digits |
| `description` | Goods description as typed (abbreviations, brands, a second language, noise) |
| `quantity` | Quantity in the declared unit |
| `unit` | pieces, kg, litres, pairs or dozens (3% carry a wrong unit on purpose: only net_kg is comparable) |
| `net_kg` | Net weight in kilograms |
| `gross_kg` | Gross weight |
| `fob_lcu` | FOB value in LCU |
| `freight_lcu` | Freight |
| `insurance_lcu` | Insurance (fob + freight + insurance = customs value) |
| `customs_value_lcu` | Customs value (CIF) in LCU |
| `invoice_currency` | Currency of the commercial invoice |
| `invoice_value` | Invoice total in that currency, on the incoterm's basis |
| `incoterm` | FOB, CIF, CFR or EXW |
| `duty_rate` | Duty rate applied (percent; 0 outside home use and under an exemption; preference caps at 5) |
| `duty_lcu` | Duty assessed |
| `vat_lcu` | Import VAT: 10% of value plus duty, home use only |
| `exemption_code` | Relief scheme (INV, DIP, AGR, EPZ) when the regime is home_use_exempt |
| `preference_claim` | none or FTA |
| `certificate_ref` | Certificate of origin reference when a preference is claimed |
| `status` | accepted, amended, withdrawn or under_query |
| `new_importer` | 1 when the importer's first line is within 12 months of the line date |
| `importer_tenure_months` | Months since the importer's registration |
| `enriched_demo` | 1 on the 20 lines of the 1B exercise (deliberately rich in findings) and nowhere else |
| `lane` | Months 1-18: green, yellow or red from the five legacy rules; months 19-36: null (no lanes) |
| `control_type` | Controls applied, or null when none took place |
| `random_draw` | 1 when the line was in the random draw (RANDOM_SHARE, drawn before the rules, stratified by office and regime) |
| `outcome` | finding or no_finding on every controlled line; null wherever no control took place (never 'no finding') |
| `finding_type` | undervaluation, misclassification, origin, quantity, prohibited or documentary |
| `duty_recovered_lcu` | Duty and VAT recovered after a finding (0 on no_finding; null without a control) |
| `control_minutes` | Officer minutes spent on the control |
| `officer_id` | Officer who controlled the line |
| `override_flag` | 1 when the lane assignment was overridden by hand (months 1-18) |
| `override_reason` | Why |
| `release_hours` | Hours from lodgement to release |

## features_lines (in addition to the line's keys, duty_rate, chapter, hs6, hs8, origin, consignment_country, regime, office, broker_id, random_draw, period_month, lane, control_type, outcome, finding_type, duty_recovered_lcu)

| Field | Meaning |
| --- | --- |
| `value_per_kg` | Customs value per kilogram (LCU) |
| `peer_median_l1` | Median value per kg of the same code and origin over the 12 months ending at the line's month |
| `peer_spread_l1` | Spread (1.4826 x MAD) at that level |
| `peer_n_l1` | Lines at that level |
| `peer_level_used` | First level with at least 30 lines: 1 code x origin, 2 code, 3 heading; 0 none |
| `peer_median_used` | Median at the level used |
| `peer_spread_used` | Spread at the level used (floor 2% of the median) |
| `peer_n_used` | Lines at the level used |
| `robust_z` | (value per kg - peer median) / spread, at the level used |
| `share_of_median` | value per kg / peer median |
| `code_drift_score` | Rise, over the trailing six months, of the share of the importer-broker pair's lines under the heading's cheapest code (0 when no rise) |
| `text_code_disagreement` | How much better another code's template fits the description than the declared code's (character n-gram similarity; 0 when unreadable) |
| `text_predicted_hs8` | The code whose template fits the description best |
| `text_higher_duty` | 1 when that code carries a higher duty than the declared one |
| `text_readable` | 1 when the description resembles any template |
| `exporter_importers_12m` | Distinct importers behind the line's seller over the trailing 12 months |
| `weight_per_unit_dev` | log(net kg per unit / usual kg per unit for the code); 0 for goods declared in kg |
| `broker_flagged_share_h1` | Share of the broker's clients with a finding in months 1-18 |
| `learned_score` | Gradient boosting trained on the months 1-18 controlled lines (label: outcome), scored on every line |
| `learned_score_red_only` | The same model trained on red-lane lines only (the selection-bias chart) |
| `oddness_score` | Isolation forest on the signals (no labels) |
| `importer_cluster` | k-means (k = 4) cluster of the importer on trader_features (1 = quietest, 4 = riskiest) |
| `desc_clean` | The description as the recipes read it: without the text in brackets, without all-capital brand words (when the text has lower-case letters), without words that contain a digit (sizes), lower-cased, single spaces |
| `usual_code` | Usual code for this description: the code most often declared with the same cleaned description in months 1-18 (8 digits; empty when the description never appears in months 1-18) |
| `usual_code_duty` | The duty (MFN, %) of the usual code |
| `duty_mfn` | The duty (MFN, %) of the declared code, from the tariff; equals duty_rate outside relief and preference |
| `kg_per_unit_ratio` | Kilos per unit against the code's usual: net kg / quantity, divided by the median of the same for that code over months 1-18; empty for goods declared in kilos |
| `desc_chapters` | Chapters this description is used under: the number of different chapters declared with the same cleaned description in months 1-18 |
| `value_vs_invoice` | Declared value against invoice x rate: the declared value on the incoterm's basis (FOB or EXW: fob_lcu; CFR: fob_lcu + freight_lcu; CIF: customs_value_lcu) divided by (invoice_value x the month's lcu_per_unit), minus 1. 0.05 means the declared value is 5% above the invoice |

## Generating rules in one paragraph each

- **Lines.** For each importer and month a Poisson count proportional to its size; the goods, origin, office and broker from the importer's own mixes; the true unit value from the code's distribution (lognormal within a cell, two grade clusters inside 40 codes, an exporter price level, a legitimate discount on 2% of lines, world price trends by chapter).
- **The seeded anomalies.** A latent anomaly on about 3% of lines, drawn from the importer's type, the duty rate, the regime, the broker, the office and the chapter; its kind drawn from the importer's preference; 18% of them leave no signal. The declaration is written from the declared values; the truth never leaves `system/`.
- **Controls.** Months 1-18: R1 new importer, R2 price below 70% of the static 2022 reference, R3 sensitive chapters at two offices, R4 preferential-origin claims from two origins, R5 the random draw before the rules, plus officer discretion; a control finds an anomaly with a probability that depends on the control type and the kind of anomaly (see calibration.md); a false finding on 0.5% of compliant controlled lines. Months 19-36: the random draw only, with a full control.
- **Other tables.** The registry and the returns follow the importer types; the mirror set sums the world's true FOB on the partner side and the declared CIF on the home side (earlier years scaled back; partner-side effects seeded); the valuation history is the world's last three months; the regional rulers are stylised statistics.
