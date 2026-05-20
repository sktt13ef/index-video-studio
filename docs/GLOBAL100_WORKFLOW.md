# Global100 Production Workflow

This workflow prepares 100 representative global index groups. Each index group is designed to produce five 60-90 second videos:

1. What the index tracks
2. Sector distribution and top holdings
3. Portfolio role
4. Historical returns, trend, maximum drawdown, and risk
5. Valuation view and data availability

The batch must not render final videos unless `data_status=ready` and `review_status=approved`.

## Build The Plan

```powershell
python build_global100_plan.py --force
```

Outputs:

- `data/global100/global100_plan.csv`
- `data/global100/profiles/{index_id}.json`
- `data/global100/sources/source_registry.json`
- `data/global100/global100_readiness_report.html`

## Dry Run Review Materials

```powershell
python render_global100_batch.py --dry-run
```

Outputs a run folder under `runs/global100_dry_run_*` with scripts, storyboards, covers, card previews, manifests, and review HTML. It does not generate voice or `final.mp4`.

## Render Guards

```powershell
python render_global100_batch.py --render-sample 5
python render_global100_batch.py --render-ready
```

These commands are guarded. They prepare review artifacts and block full rendering until data is complete and manually approved.

## Current State

At this stage, CSI 300 is the only inherited ready and approved index because it already has structured data, source cache, and sample videos. The remaining indexes require official methodology, sector weights, top holdings, history, drawdown, and valuation data before final rendering.
