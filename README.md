# Road Traffic Crashes in Uganda, 2011–2020 — Data Warehouse

This repository holds cleaned data and a reproducible correlation analysis for CUU's CAT 1 assignment. The original source is the class-provided file, **causes-of-road-traffic-crashes-in-uganda-2011-2020.xlsx**. The original Excel file is not republished here.

## Files

- `data/cleaned_crash_causes_long.csv` — 130 cause/year records with reported crash totals, severity data where provided, and data-quality flags.
- `data/annual_summary.csv` — the four variables used for the heatmap, one row per year.
- `data/data_quality_audit.csv` — missing entries and disagreements between reported totals and component sums, without invented values.
- `data/correlation_matrix.csv` — Pearson r values, computed with pairwise-complete years.
- `data/pairwise_observations.csv` — sample size for each correlation.
- `figures/pearson_correlation_heatmap.png` — labelled 4-by-4 heatmap.
- `analysis/run_analysis.py` — source cleaning and GitHub-based import/analysis code.
- `analysis/CAT1_Import_From_GitHub.ipynb` — Jupyter notebook with an explicit GitHub import, Pearson correlation calculation and heatmap.

## Replicate the GitHub-based analysis

```bash
python3 -m pip install matplotlib
python3 analysis/run_analysis.py --from-github --github-repo ggee2400/cavendish-road-safety-warehouse
```

The `--from-github` option fetches `data/annual_summary.csv` from the repository's **raw GitHub URL**, *not* a local copy.

## Classification (analytical definitions)

The original spreadsheet gives accident *causes*, not the three named aggregated variables. This study classifies:

- **Population_Behavior:** careless driving, reckless driving, careless pedestrian, over speeding, under influence of alcohol.
- **Road_Environment:** dazzled by lights, obstacle on carriage way.
- **Motor_Vehicle_Condition:** DMC (source code as labelled), over loading, dangerous loading. The latter two are vehicle-loading or operational factors rather than proof of a mechanical defect.

Passenger falls from vehicle, unknown cause and other causes remain unclassified in the three explanatory groups. **Total_Road_Traffic_Accidents** is the source's published annual grand total, not a recomputed sum.

## Data-quality principles

Blank categories were **not** changed to zero. Vehicle-condition totals are missing in 2011 and 2016 because at least one contributing category is blank. Some years' component sums disagree with the source grand total; these are recorded in the audit and not manually forced to match. The year 2011 has no fatal/serious/minor breakdown. Pearson correlations use 10 years normally, or 8 for a pair involving vehicle condition. A correlation does not establish causation; the explanatory cause groups are parts of the overall total.
