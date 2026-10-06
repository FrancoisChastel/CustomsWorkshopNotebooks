# Workshop data dictionary

Synthetic data for the IMF customs workshop. Every record and name is generated; nothing describes a real trader.
Money is in local currency units (LCU) unless the field says USD. Regenerate with `python data/generate.py --config data/config.yaml`.

## declarations

One row per declaration line, 24 months (2024-10 to 2026-09).

| Field | Meaning |
| --- | --- |
| `decl_id` | Declaration number (DCL + 7 digits) |
| `line_no` | Line number within the declaration |
| `declaration_date` | Date the declaration was lodged |
| `month` | Year-month of the declaration |
| `flow` | import, export or transit |
| `procedure` | IM4 home use, IM7 warehouse, IM5 temporary, EX1 export, TR transit |
| `office` | Customs office (see offices) |
| `trader_ref` | Customs' own trader code (always present) |
| `trader_id` | Tax ID (TIN) as customs holds it; blank for some traders, one character off for a few |
| `broker_id` | Customs broker who lodged the line |
| `exporter_id` | Foreign seller (imports and transit) |
| `consignee_id` | Who receives the goods at home (imports) |
| `ahtn8` | Declared tariff code (AHTN, 8 digits) |
| `hs6` | First six digits of the declared code |
| `description` | Goods description as typed by the declarant |
| `origin_country` | Declared country of origin ('home' for exports) |
| `shipping_country` | Country the goods were shipped from (or to, for exports) |
| `preference_claim` | none, ATIGA or other preference claimed |
| `certificate_ref` | Certificate of origin reference when a preference is claimed |
| `invoice_currency` | Currency of the commercial invoice |
| `invoice_value` | Invoice value in the invoice currency |
| `fx_rate` | Local currency units (LCU) per unit of invoice currency that month |
| `customs_value_lcu` | Customs value (CIF) in LCU |
| `net_weight_kg` | Net weight in kilograms |
| `quantity` | Quantity in the declared unit |
| `unit` | kg, tonnes, cartons, pallets or units |
| `duty_rate` | Duty rate applied, in percent |
| `duty_lcu` | Duty assessed in LCU |
| `import_vat_lcu` | Import VAT: 10% of value plus duty (home use only) |
| `relief_scheme` | Duty relief scheme used, if any |
| `new_importer` | Importer registered with customs less than 12 months before the line |
| `enriched_demo` | True on the 20 lines of the 1B exercise worksheet (deliberately rich in findings) |
| `channel` | green, yellow or red (three legacy rules) |
| `random_sample` | Drawn in the random sample before the rules ran |
| `inspected` | Physically or documentarily inspected |
| `inspection_outcome` | none or finding |
| `finding_type` | Type of finding when one was recorded |
| `duty_recovered_lcu` | Duty recovered after the finding |
| `valuation_query` | none, raised or upheld |
| `release_hours` | Hours from lodgement to release |
| `status` | accepted, amended, withdrawn or under query |

## traders

Importers and exporters as customs knows them.

| Field | Meaning |
| --- | --- |
| `trader_ref` | Customs' own trader code |
| `trader_id` | TIN as customs holds it (blank or mistyped for some) |
| `legal_name` | Registered legal name |
| `trading_name` | Name used on documents (differs for about 30%) |
| `address_id` | Address code |
| `director_id` | Director code |
| `director_name` | Director name (generated) |
| `phone` | Phone number |
| `default_broker_id` | Usual broker |
| `registration_date` | Date registered with customs |
| `sector` | Business sector (12) |
| `size_band` | S, M or L |
| `region` | Region of the head office |
| `status` | active or suspended |
| `vat_registered` | VAT registration as matched from the tax registry |
| `declared_turnover_12m` | Sales declared to tax over the last 12 months (LCU) |
| `consignee_count` | Consignees cleared under this trader |

## brokers

Licensed customs brokers.

| Field | Meaning |
| --- | --- |
| `broker_id` | Broker code |
| `name` | Broker name |
| `licence_date` | Licence date |
| `size_band` | S, M or L |

## exporters

Foreign sellers.

| Field | Meaning |
| --- | --- |
| `exporter_id` | Exporter code |
| `name` | Name (generated) |
| `country` | Country of the seller |

## consignees

Who receives imported goods.

| Field | Meaning |
| --- | --- |
| `consignee_id` | Consignee code |
| `name` | Name |
| `address_id` | Address code |
| `trader_ref` | Trader that clears for this consignee |
| `trader_id` | That trader's TIN as customs holds it |

## tariff

The 120 AHTN-8 codes used.

| Field | Meaning |
| --- | --- |
| `ahtn8` | Tariff code |
| `hs6` | 6-digit heading |
| `chapter` | 2-digit chapter |
| `description` | Description |
| `abbreviation` | Common abbreviation |
| `second_language_token` | Word often added in Thai or Vietnamese |
| `base_usd_per_kg` | World reference value per kilo (USD) |
| `duty_mfn` | MFN duty % |
| `duty_atiga` | ATIGA preferential duty % |
| `unit` | Usual trade unit |
| `typical_shipment_kg` | Typical shipment weight |
| `kg_per_unit` | Weight of one unit or carton |
| `origin_producers` | Countries that produce the goods ('|'-separated) |
| `duty_cliff_neighbour` | Neighbouring code with a lower duty |

## reference_prices

Value per kilo by code and origin over the 24 months.

| Field | Meaning |
| --- | --- |
| `ahtn8` | Tariff code |
| `origin` | Origin |
| `median_unit_value_lcu_per_kg` | Median value per kg |
| `p10` | 10th percentile |
| `p90` | 90th percentile |
| `n_lines` | Lines |

## fx_rates

Monthly exchange rates.

| Field | Meaning |
| --- | --- |
| `month` | Year-month |
| `currency` | Currency |
| `lcu_per_unit` | LCU per unit |

## offices

Customs offices.

| Field | Meaning |
| --- | --- |
| `office_id` | Office code |
| `office_name` | Name |
| `office_type` | seaport, airport, land border or dry port |

## mirror_trade

Home imports against partner exports by chapter, partner and year (USD).

| Field | Meaning |
| --- | --- |
| `chapter` | Chapter |
| `partner` | Partner country |
| `year` | Year |
| `partner_exports_usd` | Partner-reported exports to home (FOB); blank when not reported |
| `home_imports_usd` | Home-recorded imports from the partner (CIF) |
| `home_fob_usd` | Home imports at FOB |
| `freight_usd` | Freight |
| `insurance_usd` | Insurance |
| `cif_fob_adj` | Shipping-and-insurance margin for the chapter |
| `timing_usd` | Goods shipped in the year but recorded the next |
| `hub_attributed_usd` | Partner-origin goods recorded under a hub |
| `partner_weight_kg` | Partner-reported weight |
| `home_weight_kg` | Home-recorded weight |
| `reported_weight_flag` | 1 reported, 0 estimated from value |
| `attribution` | origin or consignment basis of the home record |
| `note` | Known explanation, when there is one |
| `weight_ratio` | Home weight over partner weight |

## tax_registry

The tax administration's register.

| Field | Meaning |
| --- | --- |
| `tin` | Taxpayer ID |
| `legal_name` | Name as registered (may differ in form) |
| `address_id` | Address code (blank for one) |
| `director_id` | Director code |
| `phone` | Phone |
| `region` | Region |
| `sector` | Sector |
| `vat_registered` | Registered for VAT |
| `registration_date` | Tax registration date |
| `filing_status` | filer or non-filer |

## vat_returns

Monthly VAT returns.

| Field | Meaning |
| --- | --- |
| `tin` | Taxpayer ID |
| `period` | Year-month |
| `sales_declared` | Sales declared |
| `purchases_declared` | Purchases declared |
| `import_vat_credit` | Import VAT claimed as credit |
| `filed_date` | Date filed |

## warehouse_stock

Customs warehouse (IM7) stock accounts.

| Field | Meaning |
| --- | --- |
| `operator_ref` | Warehouse operator (trader_ref) |
| `period` | Year-month |
| `opening_stock_lcu` | Opening stock |
| `entered_lcu` | Value entered |
| `exited_lcu` | Value exited |
| `declared_stock_lcu` | Closing stock declared |

## transit

Transit movements.

| Field | Meaning |
| --- | --- |
| `transit_id` | Movement ID |
| `decl_id` | Transit declaration |
| `operator_ref` | Transit operator (trader_ref) |
| `entry_office` | Entry office |
| `exit_office` | Exit office |
| `opened_at` | Opened |
| `closed_at` | Closed (blank if still open) |
| `route_norm_hours` | Normal hours for the route |
| `deadline_hours` | Deadline in hours |
| `guarantee_lcu` | Guarantee lodged |

## parcels

Low-value parcels by consignee and month.

| Field | Meaning |
| --- | --- |
| `consignee_id` | Consignee |
| `month` | Year-month |
| `consignments` | Parcels received |
| `total_value_lcu` | Total value |
| `max_value_lcu` | Largest single parcel (de minimis 2,000 LCU) |

## licences

Relief licences.

| Field | Meaning |
| --- | --- |
| `beneficiary_ref` | Beneficiary (trader_ref) |
| `scheme` | Relief scheme |
| `licence_id` | Licence |
| `licence_limit_lcu` | Value allowed per year |
| `valid_from` | From |
| `valid_to` | To |

## land_border_mirror

Imports at each land crossing against the neighbour's exports through it (LCU).

| Field | Meaning |
| --- | --- |
| `crossing_office` | Land border office |
| `neighbour` | Neighbouring country |
| `month` | Year-month |
| `home_imports_lcu` | Home-recorded imports |
| `neighbour_exports_lcu` | Neighbour-recorded exports |

## regional_unit_values

Value per kilo paid by ten importing countries (anonymised A-J) for eight goods.

| Field | Meaning |
| --- | --- |
| `year` | Year |
| `commodity` | Goods |
| `hs6` | Heading |
| `importer` | Importing country (A = home) |
| `exporter` | Exporting country |
| `uv_usd_per_kg` | Value per kilo paid |
| `uv_region_median` | Median of the ten importers |
| `uv_ratio` | Ratio to the regional median |
| `n_lines` | Lines behind the figure |
| `weight_coverage` | Share of value with a reported weight |
| `note` | Known explanation |

## sector_regional

Value-weighted ratio to the regional median by chapter and country.

| Field | Meaning |
| --- | --- |
| `year` | Year |
| `chapter` | Chapter |
| `importer` | Country (A-J) |
| `uv_ratio_to_region` | Ratio to the regional median |
| `value_usd` | Trade value |
| `weight_coverage` | Share of value with a reported weight |

## monthly_trader_uv

Monthly value per kilo for the 50 largest importers' main code, 36 months.

| Field | Meaning |
| --- | --- |
| `trader_ref` | Trader |
| `ahtn8` | Main code |
| `month` | Year-month |
| `uv_lcu_per_kg` | Value per kilo |
| `n_lines` | Lines that month |
| `ref_median` | Typical value per kilo for the code that month |

