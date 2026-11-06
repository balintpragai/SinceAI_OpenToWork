import sys, pandas as pd, numpy as np
sys.path.insert(0, '.')
from pipeline.config import Config
from pipeline import stages
from pipeline.farm import organic_share
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300); pd.set_option('display.max_columns', 30)
cfg = Config()
b = stages.stage_bronze(cfg); s1 = stages.stage_s1(b)
erp = s1['erp_purchase_lines']
miss = ['erp:4500004353:10','erp:4500004321:10','erp:4500004331:10','erp:4500005783:10','erp:4500005782:10','erp:5100000047:10']
print(erp[erp.record_key.isin(miss)][['record_key','material_id','supplier_id','quantity','uom','net_amount','currency','origin_country','lot_id','movement_type']])
sup = erp[erp.record_key.isin(miss)].supplier_id.unique()
print(erp[erp.supplier_id.isin(sup)].groupby(['supplier_id','currency','uom']).size())
x = erp[erp.material_id.isin(erp[erp.record_key.isin(miss)].material_id)]
x = x.assign(p=x.amount_eur/x.qty_kg)
print(x.groupby(['material_id','currency']).p.describe())
# soil
sh = organic_share(s1['parcels'], s1['parcel_crop_history_and_plan'])
sv = s1['farm_survey'].merge(sh, on=['farm_id','crop','year'], how='left')
ms = ['farm_survey:FS00200','farm_survey:FS00600','farm_survey:FS00623','farm_survey:FS01314','farm_survey:FS01323','farm_survey:FS01990','farm_survey:FS02440','farm_survey:FS02702','farm_survey:FS02889','farm_survey:FS02890']
print(sv[sv.record_key.isin(ms)][['record_key','farm_id','crop','year','area_ha','declared_area_ha','organic_ha','organic_share','n_parcels','yield_t_ha','lime_t_ha','n_mineral_kg_ha']])
p = s1['parcels']
for fid in sv[sv.record_key.isin(ms)].farm_id.unique()[:4]:
    print(p[p.farm_id==fid][['parcel_id','area_ha','soil_class_soilmap','clay_pct_soilmap','slope_pct','p_test_mgl_latest','drainage']].to_string(index=False))
