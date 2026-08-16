# simulator Retirement Record

## Decision

The standalone Streamlit Acquisition Simulator is retired from the portfolio architecture. Power BI remains the only business-facing decision surface, while the validation layer retains all model sensitivity and scenario analysis.

## Inspection result

The retired `app/` tree consisted of Streamlit page composition, controls, charts, recommendation text, and service wrappers. Its scoring and scenario services did not own the analytical methodology: they delegated to or repeated behavior already available in the scoring engine and validation model-validation modules.

The authoritative reusable logic remains in:

- `python/analysis/scoring_engine.py` for base scoring and segmentation;
- `python/model_validation/sensitivity.py` for scenario reweighting and rank stability;
- `python/model_validation/diagnostics.py` and `stress_tests.py` for model validation; and
- the validation notebooks, processed exports, and validation artifacts.

No function needed by the scoring engine, validation, dashboard, PostgreSQL, or SQL analytics was deleted.

## Removed application-only surface

- `.streamlit/config.toml`
- `app/` and its components, services, configuration, and README
- `python/analysis/validate_simulator.py`
- `tests/test_simulator.py`
- `documentation/methodology/simulator.md`
- generated `validation/simulator_*` simulator audit artifacts
- Streamlit and Altair declarations from `requirements.txt`
- simulator Make targets

Generated caches and simulator screenshots were removed from the project tree. An already-created local virtual environment may still contain previously installed package binaries; those are not declared project dependencies and are not part of the repository architecture.

## Preserved analytical assets

- `data/powerbi/DimScenario.csv` with 11 curated scenarios
- `data/powerbi/FactScenarioScore.csv` with 1,320 lot-scenario rows
- `data/powerbi/FactScenarioComponent.csv` with 6,600 component rows
- `data/powerbi/FactLocalityScenario.csv` with locality scenario summaries
- validation sensitivity, revenue-sensitivity, locality-sensitivity, rank-stability, stress-test, and monotonicity outputs
- Power BI robustness and scenario field mappings

## Reference audit

Repository references to Streamlit or the simulator are now limited to explicit retirement notes and regression checks. No audit implementation document references the simulator as a required component.

## Regression guard

`tests/test_dashboard.py` verifies that the application surface and dependencies remain absent while the validation sensitivity assets retain their expected grain.
