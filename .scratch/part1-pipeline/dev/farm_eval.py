import sys, pandas as pd, numpy as np
sys.path.insert(0, '.')
from deltalake import DeltaTable
import pipeline.farm as farm
from pipeline.canonical import farm_footprints
def t(n): return DeltaTable(f'lakehouse/Tables/{n}').to_pandas()
s3 = {n: t('s3_'+n) for n in ['farm_survey','parcels','parcel_crop_history_and_plan','erp_purchase_lines']}
for k in s3: 
    for c in ('is_excluded','is_estimate','has_flag'):
        if c in s3[k]: s3[k][c] = s3[k][c].astype(bool)
erp = s3['erp_purchase_lines']; erp = erp[~erp.is_excluded]
summ = t('gold_inventory_summary')
truth = {2023: 217542.90, 2024: 172084.85}
base_ff, _ = farm_footprints(s3, erp)
base = base_ff.groupby('year').tco2e.sum()
ours = summ[summ.category=='cat01_purchased_goods_services'].set_index('year').tco2e
print('farm totals', base.round(0).to_dict())
print('component share 2024', (base_ff[base_ff.year==2024][[c+'_tco2e' for c in farm.COMPONENTS]].sum()/base[2024]).round(3).to_dict())
p0 = s3['parcels'].copy()
def run(mask, name):
    p = p0.copy(); p['soil_class_soilmap'] = np.where(mask(p), 'organic', np.where(p.soil_class_soilmap=='organic','clay_x',p.soil_class_soilmap))
    s = dict(s3); s['parcels'] = p
    ff, _ = farm_footprints(s, erp)
    tot = ff.groupby('year').tco2e.sum()
    errs = {y: round((ours[y] - base[y] + tot[y]) / truth[y] * 100 - 100, 2) for y in truth}
    print(f'{name:45s}', errs)
run(lambda p: p.soil_class_soilmap=='organic', 'soilmap')
for X in (10, 15, 20, 25):
    run(lambda p, X=X: (p.soil_class_soilmap=='organic') | ((p.soil_class_soilmap=='clay') & (p.clay_pct_soilmap<=X)), f'+clay<= {X}')
run(lambda p: ((p.soil_class_soilmap=='organic') & (p.clay_pct_soilmap<=25)) | ((p.soil_class_soilmap=='clay') & (p.clay_pct_soilmap<=20)), 'org<=25 + clay<=20')
