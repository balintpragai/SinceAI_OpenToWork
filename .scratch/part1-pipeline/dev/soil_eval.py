import sys, pandas as pd, numpy as np
sys.path.insert(0, '.')
from pipeline.config import Config
from pipeline import stages
pd.set_option('display.width', 250)
cfg = Config()
b = stages.stage_bronze(cfg); s1 = stages.stage_s1(b)
p = s1['parcels']; ch = s1['parcel_crop_history_and_plan']; sv = s1['farm_survey']
key = pd.read_csv(cfg.package_root / 'tasks/dev/A1_dev_issue_labels_2023_2024.csv')
lab = key[key.issue_type=='soil_misreport']
truth_share = lab.set_index('record_key').true_value.str.extract(r'([\d.]+)')[0].astype(float)
dev = sv[sv.year.isin([2023,2024]) & ~sv.organic_reported].copy()
dev['y'] = dev.record_key.isin(lab.record_key)
c = ch[ch.status=='declared'].merge(p, on=['parcel_id','farm_id'], how='left')
def evaluate(org_mask, name):
    cc = c.assign(org=np.where(org_mask.reindex(c.parcel_id).values, c.area_ha, 0.0))
    g = cc.groupby(['farm_id','crop','year']).agg(a=('area_ha','sum'), o=('org','sum')).reset_index()
    g['share'] = g.o/g.a
    d = dev.merge(g, on=['farm_id','crop','year'], how='left')
    for th in (0.3,):
        pred = d.share >= th
        tp = (pred & d.y).sum(); fp = (pred & ~d.y).sum(); fn = (~pred & d.y).sum()
        f1 = 2*tp/(2*tp+fp+fn)
        print(f'{name:40s} th={th} tp={tp} fp={fp} fn={fn} f1={f1:.3f}')
    return d
pi = p.set_index('parcel_id')
evaluate(pi.soil_class_soilmap=='organic', 'soilmap organic')
for X in (5, 8, 10, 12, 15, 20, 25):
    evaluate((pi.soil_class_soilmap=='organic') | ((pi.soil_class_soilmap=='clay') & (pi.clay_pct_soilmap<=X)), f'+clay<= {X}')
d = evaluate((pi.soil_class_soilmap=='organic') | ((pi.soil_class_soilmap=='clay') & (pi.clay_pct_soilmap<=20)), 'chk')
d['ts'] = d.record_key.map(truth_share)
print(d[d.y][['record_key','share','ts']].assign(diff=lambda x: x.share-x.ts).describe())
