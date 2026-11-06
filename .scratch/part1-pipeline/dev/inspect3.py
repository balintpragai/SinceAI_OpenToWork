import sys, pandas as pd, numpy as np
sys.path.insert(0, '.')
from pipeline.config import Config
from pipeline import stages
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300); pd.set_option('display.max_columns', 30)
cfg = Config()
b = stages.stage_bronze(cfg); s1 = stages.stage_s1(b)
p = s1['parcels']
print(p.groupby('soil_class_soilmap').clay_pct_soilmap.describe())
print(pd.crosstab(p.soil_class_soilmap, pd.cut(p.clay_pct_soilmap,[-1,5,10,15,20,25,30,40,60,100])))
print(pd.crosstab(p.soil_class_soilmap, p.drainage, normalize='index'))
print(p.groupby('soil_class_soilmap')[['slope_pct','p_test_mgl_latest','dist_to_water_m']].median())
erp = s1['erp_purchase_lines']; e = erp[erp.uom=='EUR'].copy()
e['r'] = e.amount_eur / e.groupby('material_id').amount_eur.transform('median')
print(e.sort_values('r', ascending=False)[['record_key','material_id','supplier_id','amount_eur','r','year']].head(25))
