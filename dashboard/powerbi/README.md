# PARK It Up Power BI Decision Dashboard Package

## Status

Power BI Desktop, PBIP tooling, Tabular Editor, and DAX Studio were not available in the development environment (macOS ARM64). No `.pbix` or `.pbip` file is claimed or included.

This directory is the complete assembly package for Power BI Desktop:

- star-schema model and relationship specification;
- exact PostgreSQL and portable-CSV source mappings;
- DAX measure definitions, including the redesign additions;
- five page-by-page visual and interaction specifications;
- a design system in [theme.md](theme.md) and a theme JSON;
- a keep/remove record for every visual in [visual_inventory.md](visual_inventory.md);
- actual-data static page previews in `screenshots/`;
- the dashboard-redesign UX redesign rationale and validation record;
- validation results produced before handoff.

The mockups are design previews, not screenshots of a running Power BI report. They use the same fields and current values that the report is specified to display.

## Build order on a Power BI machine

1. Run `make powerbi-data` from the repository root. This refreshes the portable star-schema extracts after the validation layer.
2. Open Power BI Desktop and choose **Get data > PostgreSQL** for the primary source. Use the queries and views in [data_sources.md](data_sources.md).
3. Alternatively, import the CSVs in `data/powerbi/` for a portable review build. The CSVs are generated extracts, not a second source of truth.
4. Create the relationships in [relationships.md](relationships.md), keeping single-direction filtering from dimensions to facts.
5. Add the measures from [dax_measures.md](dax_measures.md). Use `DIVIDE` for every ratio and leave `AggBDFunnel`/`AggBDConversion` hidden as reconciliation references; dynamic funnel visuals use `FactOutreach`.
6. Apply `parkitup_theme.json`.
7. Build the five pages in the order in [page_01_executive.md](page_01_executive.md) through [page_05_bd_strategy.md](page_05_bd_strategy.md).
8. Reconcile the values against [validation.md](validation.md) and `validation/powerbi_reconciliation.csv` before publishing.

## Runbook

```bash
make validate-all       # refresh validated validation outputs first
make powerbi-data      # prepare and reconcile the star-schema extracts
make powerbi-pages   # regenerate the five static page previews
make powerbi           # run both dashboard steps
make dashboard          # regenerate and test the dashboard redesigned previews
```

The current visual direction is documented in [redesign.md](redesign.md), with repository-side checks in [redesign_validation.md](redesign_validation.md). The redesign uses a compact horizontal navigator and a persistent scope/scenario header, gives each page a single dominant visual, and cuts the report from 34 visual elements to 22. It does not alter the model, the scoring methodology, or add a second application surface.

Layout integrity is enforced mechanically. `python/visualization/design_system.py` holds the grid, palette and card/plot-area primitives; `python/visualization/layout_audit.py` rebuilds every page and fails if any chart's tick labels, axis titles or in-chart text escape the card hosting them.

## Current base-case headline values

These are generated, not hard-coded in the report:

- 120 parking lots and 23,685 spaces;
- 25 `ACQUIRE_NOW` targets;
- INR 6,052,473 modelled monthly platform-revenue potential;
- six `STRONG` localities under the documented market classification;
- 45.17 average acquisition score;
- 33.90% average observed occupancy using the daily-fact measure;
- 10.0% synthetic BD lead-to-onboarded conversion.

## Relationship to the rest of the project

Power BI is the single business-facing reporting layer. validation Python remains the validation and sensitivity layer, including the eleven-scenario history and rank-stability outputs. The dashboard should read the validated analytics views and validation exports rather than reimplementing the scoring engine. The former Streamlit simulator was retired to keep the portfolio focused and is not a project dependency.

## Known limitations

- No Power BI Desktop interaction test could be executed here; validation covers the source model, DAX-equivalent Python measures, keys, filters, and Top-10 reconciliation.
- The map preview uses latitude/longitude bubbles without a live basemap. Add Power BI Azure Maps or Map when assembling the report, with a visible synthetic-data note.
- Scenario outputs are the validation 11-scenario set. They are conditional robustness diagnostics, not forecasts.
- Monetary values are modelled gross platform revenue, not profit.
- Operational, economic, owner, network, and outreach values are synthetic.
