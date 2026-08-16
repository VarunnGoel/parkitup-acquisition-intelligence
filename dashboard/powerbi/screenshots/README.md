# Page previews

Five static, actual-data design previews of the Power BI pages, one per page, at
1920x1080 (16:9).

These are **implementation previews, not screenshots of a running PBIX file**.
Power BI Desktop is unavailable on the development host, so the pages are
rendered from the same extracts in `data/powerbi/` that the report is specified
to read. Every number shown is generated, not typed.

Regenerate with `make dashboard`, which also runs the layout audit and the
Dashboard tests.

| File | Page | Business question | Primary visual |
| --- | --- | --- | --- |
| `page_01_executive_overview.png` | Executive Overview | Where is the biggest acquisition opportunity? | Opportunity map |
| `page_02_market_opportunity.png` | Market Opportunity | Which markets should PARK It Up expand in? | Demand against current coverage |
| `page_03_acquisition_matrix.png` | Acquisition Priority | Which parking lots should the BD team pursue? | Attractiveness against feasibility |
| `page_04_parking_deep_dive.png` | Parking Lot Deep Dive | Why should PARK It Up acquire this lot? | Score breakdown with locality markers |
| `page_05_bd_strategy.png` | BD Action Center | What should the BD team do next? | Pipeline funnel |

Typography differs from the Power BI target in one respect: the report theme
specifies Aptos, and these previews render in Lato because Aptos is not installed
in the rendering environment. Sizes, weights and hierarchy match the theme.
