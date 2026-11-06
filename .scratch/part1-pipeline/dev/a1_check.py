import sys, pandas as pd
sys.path.insert(0, '.')
from pipeline.config import Config
from pipeline import stages
from pipeline.refdata import ccn_score
cfg = Config()
cfg.raw_dir.mkdir(parents=True, exist_ok=True)
stages.stage_raw(cfg)
b = stages.stage_bronze(cfg); s1 = stages.stage_s1(b); ctx = stages.make_context(s1)
log = stages.stage_s2(ctx)
log.to_pickle('.scratch/part1-pipeline/dev/issues.pkl')
key = pd.read_csv(cfg.package_root / 'tasks/dev/A1_dev_issue_labels_2023_2024.csv')
sub = log[log.year.isin([2023, 2024])].rename(columns={})[['table','record_key','issue_type','confidence','year']]
print(ccn_score.score_a1(sub, key, [2023, 2024]))
k = key.groupby('record_key').issue_type.apply(set)
s = sub.drop_duplicates('record_key').set_index('record_key')
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300)
summ = []
for (t, it), g in log[log.year.isin([2023,2024])].groupby(['table','issue_type']):
    tp = g.record_key.isin(k.index).sum()
    summ.append((t, it, len(g), tp))
for (t, it), g in key.groupby(['table','issue_type']):
    summ.append((t, it, 'TRUE', len(g)))
print(pd.DataFrame(summ, columns=['table','type','flagged','tp/true']).sort_values(['table','type']).to_string(index=False))
print('per year counts all:'); print(log.groupby(['table','issue_type','year'],dropna=False).size().unstack(fill_value=0))
