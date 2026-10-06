# Customs workshop notebooks and data

Material for the customs breakouts of the workshop **Data Driven Domestic Revenue Mobilization**
(Bangkok, 19–22 October 2026), organised by the IMF Fiscal Affairs Department.

Everything here is synthetic. Every trader, declaration and name is generated, and nothing
describes a real company or person. Answers and facilitator notes are not in this repository.

## What is here

| Folder | Contents |
| --- | --- |
| `data/` | The 20 workshop tables (CSV and Parquet), the session worksheets (JSON) and the data dictionary ([data/README.md](data/README.md)) |
| `workshop_methods/` | The methods used in the sessions, as a small Python package |

## Use it in Python or Google Colab

```python
!git clone -q https://github.com/FrancoisChastel/CustomsWorkshopNotebooks.git
%cd CustomsWorkshopNotebooks
!pip install -q .

from workshop_methods.data import load_tables
tables = load_tables("data")
tables["declarations"].head()
```

Without cloning, `load_tables("https://raw.githubusercontent.com/FrancoisChastel/CustomsWorkshopNotebooks/main/data")`
reads the CSV files over HTTPS.

Keep the code columns as text when you read a CSV yourself (`ahtn8`, `hs6`, `chapter`, `month`,
`period`, `trader_id`, `tin`): `load_tables` does this for you.

## Data versions

The tables are generated from one seed, so the same version always holds the same numbers. Each
release (`data-v1`, `data-v2`, …) is fixed. The workshop laptops download its `workshop-data.zip`
(CSV, worksheets and dictionary) when the workshop kit is set up.
