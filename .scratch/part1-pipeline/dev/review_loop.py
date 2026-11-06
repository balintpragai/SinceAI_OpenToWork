"""Simulates the dashboard: writes review decisions, then the pipeline reruns."""
import sys, pandas as pd
sys.path.insert(0, '.')
from deltalake import DeltaTable, write_deltalake
iss = DeltaTable('lakehouse/Tables/gold_issues').to_pandas()
a = iss[(iss.year == 2025) & (iss.issue_type == 'area_mismatch')].iloc[0]
b = iss[(iss.year == 2025) & (iss.issue_type == 'outlier_implausible')].iloc[0]
dec = pd.DataFrame([
    dict(decision_id='d1', issue_id=a.issue_id, decision='reject', override_field=None, override_value=None, reviewer='reviewer.test', decided_at='2026-11-07T08:00:00Z', comment='area confirmed by farmer'),
    dict(decision_id='d2', issue_id=b.issue_id, decision='override', override_field='yield_t_ha', override_value=str(float(b.proposed_value)), reviewer='reviewer.test', decided_at='2026-11-07T08:01:00Z', comment='decimal slip'),
    dict(decision_id='d3', issue_id=None, decision='sign_off', override_field='inventory_year', override_value='2025', reviewer='reviewer.test', decided_at='2026-11-07T08:05:00Z', comment='2025 inventory approved'),
]).astype('string')
write_deltalake('lakehouse/Tables/review_decisions', dec, mode='overwrite', schema_mode='overwrite')
print('rejected', a.record_key, '| overridden', b.record_key, b.observed_value, '->', b.proposed_value)
