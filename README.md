# Where Should Korea Build Its Next Workation Hub?

**A full-population diagnostic of all 89 population-declining regions in South Korea, ranking them by the *quality of stay* rather than the volume of visitors.**

Submitted to the **2026 Korea Tourism DataLab Utilization Competition** (2026 한국관광 데이터랩 활용 경진대회), hosted by the Ministry of Culture, Sports and Tourism and the Korea Tourism Organization.

---

## The problem

South Korea has designated 89 municipalities as *population-declining regions* (인구감소지역). For these places, growing the registered resident population is no longer a realistic goal, so national policy has shifted toward growing the **"de facto" population** — people who stay, work and spend there without moving in. The flagship instrument for this is **workation**: remote work from a vacation destination.

But there is no quantitative basis for deciding **where to build workation infrastructure first**. Designations have tended to follow whichever municipality applied most aggressively, or which name is already familiar. Meanwhile:

> Of the **905** shared-office facilities in South Korea, **808 (89.3%)** are in the Seoul metropolitan area — and **exactly 0** are located in any of the 89 population-declining regions.

The private sector has skipped these regions entirely. Whatever gets built, the government builds. That makes "where first" a decision worth getting right.

## The core idea

The conventional proxy for tourism potential is **visitor volume**. This project argues that for workation the relevant signal is the **quality of stay** — how long people stay, whether they sleep there, and whether that behaviour is trending up.

Two independent axes are measured for every region:

| Axis | Definition |
|---|---|
| **Stay Maturity** | Standardised sum of average dwell time, average nights per stay, and share of overnight visitors — *how workation-like the region already is* |
| **Growth Momentum** | Model-predicted 12-month growth in visitor volume — *whether stay demand is accelerating* |

The two turn out to be **statistically independent** (Spearman ρ = **−0.15**, p = 0.17). A single ranked index would therefore destroy information, so regions are placed on a **2 × 2 frame** instead of a leaderboard:

| Quadrant | Regions | Meaning |
|---|---|---|
| Accelerating workation type | 19 | Already workation-like **and** growing → build now |
| Emerging potential | 26 | Growing but not yet workation-like → cultivate |
| Mature but stalled | 26 | Workation-like but flat → reactivate |
| Low potential | 18 | Monitor |

## Three findings

**1 · The infrastructure gap is total, not partial.**
Zero of 905 shared offices sit in the 89 regions. This is not a "lagging region" story; it is a market that does not exist.

**2 · The de-facto-population multiplier is a trap if you read its level.**
The ratio of de facto population to registered population looks like an obvious indicator of a region's pull. But its **level** correlates *negatively* with investment priority (ρ = **−0.43**) — it peaks in seasonal beach destinations that empty out for ten months a year. Only its **trend** carries independent signal, agreeing with the model's growth prediction at ρ = **+0.50**. Level was discarded; trend was kept.

**3 · Designation alone produces no measurable effect.**
Comparing 9 designated regions against 62 undesignated ones with difference-in-differences and two-way fixed effects, **no aggregate effect is detectable** (DiD = +0.002, permutation p = 0.93). Designated-programme participants are too few to move regional aggregates. The policy implication is not "designation doesn't work" but **"designation without physical infrastructure doesn't work."**

## How the design was reached — three rejected hypotheses

The final frame is what survived. Each earlier attempt was discarded on evidence, and the record is preserved in [`docs/devlog/`](docs/devlog/).

| # | Hypothesis | What the data said | Outcome |
|---|---|---|---|
| 1 | Rank regions with a single composite index | Weighted-sum vs. PCA rankings agreed at only ρ = 0.22 — the ranking was an artefact of arbitrary weights | **Index abandoned** |
| 2 | Rank regions by predicted growth rate | Time-split R² ≈ 0 across 6 model families. Region-split R² = 0.12, direction accuracy 0.69 | **Role redefined** — the model explains drivers and produces *relative* rankings, never point forecasts |
| 3 | Use the de-facto-population multiplier level | Negative correlation with priority (−0.43); seasonal destinations dominate | **Level dropped, trend kept** |

A fourth turn was the pivot itself: once the two axes were measured *against each other* and found independent, one-dimensional ranking became indefensible and the 2 × 2 frame replaced it.

Clustering was also tried and rejected as the primary typology — silhouette peaked at 0.24, indicating a continuous spectrum rather than natural groups. Time-series trajectory clustering was retained as a *secondary* lens, and it caught something the static frame missed: **7 regions classified "mature but stalled" are in fact deepening their overnight-stay behaviour**, making them cheap reactivation targets.

## Validation — including what failed

Honest reporting of both outcomes matters more here than a clean result.

| Test | Result |
|---|---|
| **Construct validity** — is Stay Maturity actually higher in regions that run workation programmes? Computed from **2022 data only**, compared against the 27 regions later confirmed to be designated or operating | Mann-Whitney one-sided **p = 0.046 — significant** |
| **Foresight** — did the 2022-only ranking anticipate the 11 *new* designations made in 2024–25? | Hypergeometric **p = 0.29 — not significant.** 5 of 11 landed in the top 30 (1.35× chance), but the sample is too small to support the claim |
| **External case** — where does the model place **Gangjin-gun**, the local government that won the grand prize in the 2025 edition of this same competition? | Classified **Tier 1 (top 13 of 89)**, with no information about that award anywhere in the model inputs |

An earlier draft led with the foresight result. Re-checking showed it was not significant and that moving the cut-off until it became significant would be p-hacking, so the primary claim was replaced with the cut-off-free test and the negative result was kept in the write-up as a stated limitation. See [`docs/devlog/19_재검증-및-수치교정.md`](docs/devlog/19_재검증-및-수치교정.md).

## Output — a prioritised action map

All 89 regions are sorted into five action tiers by a priority score combining growth momentum, long-term population decline, stay maturity, external overnight-stay interest, and de-facto-population trend.

| Tier | Regions | Recommended action |
|---|---|---|
| **Tier 1 — invest now** | **13** | Build shared offices and medium-stay lodging directly |
| Tier 1− | 6 | Same investment, lower demographic urgency |
| **Tier 2 — cultivate** | 26 | Design a workation package (space + lodging + programme) |
| Tier 3 — reactivate | 26 | Revisit / long-stay marketing (7 overnight-deepening regions first) |
| Monitor | 18 | Track leading indicators quarterly |

**Tier 1**: Wando, Buyeo, Haenam, Goheung, Yeongam, Yeongwol, Yeongju, Busan Seo-gu, Yeongdong, Jeongeup, Hapcheon, Gangjin, Seocheon.

A scenario estimate sizes the opportunity: roughly **KRW 19.5bn** to establish hubs across the 13 Tier 1 regions could yield **KRW 41.4–145.0bn** in additional annual tourism spending by year three (2.1×–7.4× return). This is **an assumption-driven scenario, not a causal forecast** — and the write-up states explicitly where the assumption sits in the observed distribution: the +0.20/+0.35 multiplier uplift is *upper-quartile*, not conservative, with the 13-region median at +0.10, which is why a floor scenario was added.

## Interactive dashboards

Both are **single self-contained HTML files** — no server, no build step, no network access required. Clone and open in a browser.

| File | What it does |
|---|---|
| [`report/진단대시보드.html`](report/진단대시보드.html) | All 89 regions on the 2 × 2 scatter, plus a sortable and filterable diagnostic table |
| [`report/대시보드_공유용.html`](report/대시보드_공유용.html) | Region-level card view: metric strip, comparison bars against the 89-region median, 48-month sparklines, recommended action, impact scenarios, quarterly KPIs |

Both are theme-aware (light/dark) and were render-verified in headless Chrome — 89 plotted points, 89 table rows, zero console errors.

## Repository layout

```
├── *.py                      analysis pipeline (numbered in execution order)
├── viz_style.py              shared plotting design system
├── report/                   dashboards (self-contained HTML) + Tier 1 action scenarios
├── outputs/
│   ├── tables/               every number in the write-up traces back to here
│   └── figures/              submission figures (sub_*) + intermediate round figures
└── docs/
    ├── submission_writeup_ko.md    the competition write-up (Korean)
    └── devlog/                     development diary — 19 entries, in order
```

### Pipeline order

```
collect    download_datalab.py · fetch_living_population.py · fetch_age_population.py
           build_population.py · scrape_workation.py → build_workation_labels.py
           build_office_features.py
merge      process_datalab.py → process_static.py → process_sukbak.py
           build_master_table.py                      → 4,806 rows × 113 features
analyse    04_eda → 05_baseline_index → 06_forecast_model → 07_shap_and_index_v1
           → 08_clustering → 09_policy_matching → 10_living_population
           → 11_integrate_validate → 12_event_study → 13_trajectory_clustering
           → 17_impact_projection → 18_backtest_frame
visualise  viz_style.py + 20~25_fig_*.py · 26_prep_dashboard_data.py
```

## Data

| Source | Used for |
|---|---|
| **Korea Tourism DataLab** (datalab.visitkorea.or.kr) | Visitor counts, dwell time, nights per stay, overnight share, card-based tourism spending — 89 regions × 54 months (2022.01–2026.06), 801 files collected |
| **KOSIS** (National Statistics Portal) | De facto population, registered population by 5-year age band |
| **Public Data Portal** (Korea Culture Information Service Agency) | National shared-office facility registry |
| **Ministry of the Interior and Safety** | Population-declining region designations |

**Source datasets are not redistributed in this repository.** DataLab requires an account and its terms restrict redistribution, so `datalab_raw/` and the derived `processed/` panels are excluded. The collection scripts reproduce them. Aggregated analysis outputs in `outputs/tables/` **are** included — every figure in the write-up can be traced to them without re-running collection.

API keys are read from environment variables (`KOSIS_API_KEY`, `TOUR_API_KEY`) and are never hard-coded.

### Environment

Python 3.14 — pandas, numpy, scikit-learn, lightgbm, shap, statsmodels, tslearn, matplotlib, selenium.

## Limitations

- De facto population statistics have only been published since 2024, so they enter as a cross-sectional indicator rather than a full time series.
- No official consolidated list of workation-designated regions is published. The validation labels are a curated cross-reference of multiple sources and may be incomplete — which directly limits how strongly the validation results can be read.
- The impact estimate is a **scenario built on an assumed multiplier uplift**, not a causal estimate. The designation effect study found no causal effect to extrapolate from.
- Supply-side capacity (existing lodging inventory, land availability) is not modelled.
- The forecasting model is used for relative ranking and driver attribution only. Time-split R² is approximately zero; it cannot forecast a specific region's growth rate.

## License

Code is released under the [MIT License](LICENSE). Figures, tables and written analysis are released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Underlying source data remains subject to the terms of its respective providers.
