import sys, pandas as pd, numpy as np
sys.path.insert(0, '.')
from deltalake import DeltaTable
from pipeline.canonical import farm_footprints
def t(n): return DeltaTable(f'lakehouse/Tables/{n}').to_pandas()
s3 = {n: t('s3_'+n) for n in ['farm_survey','parcels','parcel_crop_history_and_plan','erp_purchase_lines']}
for k in s3:
    for c in ('is_excluded','is_estimate','has_flag'):
        if c in s3[k]: s3[k][c] = s3[k][c].astype(bool)
erp = s3['erp_purchase_lines']; erp = erp[~erp.is_excluded]
summ = t('gold_inventory_summary'); ours = summ[summ.category=='cat01_purchased_goods_services'].set_index('year').tco2e
truth = {2023: 217542.90, 2024: 172084.85}
base = farm_footprints(s3, erp, 0.0)[0].groupby('year').tco2e.sum()
for w in (0.0, 0.3, 0.35, 0.4, 0.42, 0.45, 0.5):
    tot = farm_footprints(s3, erp, w)[0].groupby('year').tco2e.sum()
    print(w, {y: round((ours[y] - base[y] + tot[y]) / truth[y] * 100 - 100, 3) for y in truth})
