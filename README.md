# E-commerce Python Analytics

Reusable Python analysis scripts for Shopify-style exports, marketing attribution, email performance, order reconciliation, sales trends, and inventory analysis.

**Prepared by Tomas Corza**

## Scripts

| Script | Purpose | Source status |
| --- | --- | --- |
| `scripts/shopify_order_checks.py` | Order/line-item reconciliation, duplicate IDs, UTM ambiguity | Adapted from an earlier working script |
| `scripts/shopify_profit_reconciliation.py` | Order profitability and UTM-associated sales reconciliation | Adapted from an earlier working script |
| `scripts/email_marketing_audit.py` | Shopify and Klaviyo flows/campaign performance and send-time analysis | Adapted from an earlier working script |
| `scripts/sales_trends.py` | Daily and monthly sales, MoM and YoY changes | Reconstructed reusable implementation |
| `scripts/campaign_performance.py` | Ad spend vs attributed orders and revenue | Reconstructed reusable implementation |
| `scripts/inventory_history.py` | Historically selling variants with no observed stock | Reconstructed reusable implementation |

Recovered scripts were **adapted for a generic public-facing library**, not preserved byte-for-byte. Reconstructed tools represent earlier workflows, not recovered original code. The three adapted scripts preserve some original export schemas and may need column mapping for other stores.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

## Quick start (using synthetic examples)

```bash
python scripts/sales_trends.py examples/daily_sales.csv
python scripts/campaign_performance.py examples/campaign_spend.csv examples/campaign_sales.csv
python scripts/inventory_history.py examples/inventory_snapshots.csv examples/variant_sales.csv
```

Reports are saved to `output/` (ignored by Git).

## Shopify export reconciliation

Place the following **private** CSV files in one local folder (the scripts never include real store data in this repository):

- `Shopify_Order_Level.csv`
- `Shopify_Order_Level_Attribution.csv`
- `Shopify_Order_Line_Profitability.csv`

Run:

```bash
python scripts/shopify_order_checks.py /path/to/private/exports
python scripts/shopify_profit_reconciliation.py /path/to/private/exports
```

The more detailed reconciliation optionally reads `Shopify_Monthly_Profitability.csv` and requires extra export fields (see `required` near the top of that script). Never interpret a UTM indicator as proof of incremental sales or an order-level Klaviyo conversion match.

## Email reporting

`email_marketing_audit.py` optionally reads `Shopify_Daily_Profitability.csv`, `Klaviyo_Flows_Part*.csv` (or `Klaviyo_Flows_Annual.csv`) and `Klaviyo_Campaigns_Annual.csv`. Date filtering can be configured:

```bash
REPORT_START=2025-01-01 REPORT_END=2025-12-31 python scripts/email_marketing_audit.py /path/to/private/exports
```

This is a descriptive audit; overlapping attribution and source export grains can overstate apparent revenue. Confirm timezone before using send-hour findings.

## Data and limitations

- Example CSVs are fictional. No customer, employer, store, or campaign-level actuals are included.
- `inventory_history.py` identifies **no observed positive stock in supplied snapshots**, not proof that an item was never stocked.
- Input formats differ across Shopify, Klaviyo, ad platforms, and export versions. Inspect column names and adjust when needed.
- MoM/YoY calculations require continuous and comparable reporting periods; partial months can be misleading.
- No license is granted by this repository. Copyright © 2026 Tomas Corza for original documentation and organization, subject to any third-party rights.

## Publication note

This library intentionally excludes real data and employer identifiers. That does **not** establish ownership or permission to publish code created during employment. Review applicable agreements before making a public repository.


## Portable use with independently authorized data

The committed examples are fictional and are intended to exercise the analysis scripts without a live store. For another organization, use that organization's authorized exports in a local, non-version-controlled directory; verify column names, currency, reporting windows, and attribution definitions before relying on results. Do not copy customer-level exports, tokens, or confidential reporting from a previous organization. Existing scripts and calculation logic are unchanged by this documentation update.

**Provenance:** Some scripts are adapted from earlier analysis work, as identified above. Their general applicability does not establish ownership or permission to redistribute any protected implementation.
