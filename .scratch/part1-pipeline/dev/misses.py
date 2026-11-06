import sys, pandas as pd
sys.path.insert(0, '.')
from pipeline.config import Config
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300); pd.set_option('display.max_colwidth', 90)
cfg = Config()
log = pd.read_pickle('.scratch/part1-pipeline/dev/issues.pkl')
key = pd.read_csv(cfg.package_root / 'tasks/dev/A1_dev_issue_labels_2023_2024.csv')
dev = log[log.year.isin([2023, 2024])]
miss = key[~key.record_key.isin(dev.record_key)]
print('MISSED'); print(miss.drop(columns=['issue_id']).to_string(index=False))
fp = dev[~dev.record_key.isin(key.record_key)]
print('FALSE POS'); print(fp[['record_key','issue_type','confidence','evidence']].to_string(index=False))
