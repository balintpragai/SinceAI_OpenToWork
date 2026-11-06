import pandas as pd, numpy as np
from deltalake import DeltaTable
e = DeltaTable('lakehouse/Tables/s3_energy_meter_readings').to_pandas()
e = e[~e.is_estimate.astype(bool) & (e.mwh > 0)]
sales = DeltaTable('lakehouse/Tables/s3_sales_volumes').to_pandas().groupby(['site_id','year','month']).t_sold.sum()
res = []
for (s, c), g in e.groupby(['site_id','carrier']):
    piv = g.pivot_table(index='year', columns='month', values='mwh', aggfunc='sum')
    comp = piv.dropna()
    if len(comp) < 3: continue
    for y in comp.index:
        for m in range(1, 13):
            true = comp.loc[y, m]
            others = comp.drop(index=y)
            sh = others.div(others.sum(axis=1), axis=0)
            avail = comp.loc[y].drop(m)
            # A: median share (current)
            shA = sh.median(); shA = shA/shA.sum()
            A = avail.sum()/shA[avail.index].sum()*shA[m]
            # B: mean share
            shB = sh.mean(); shB = shB/shB.sum()
            B = avail.sum()/shB[avail.index].sum()*shB[m]
            # C: nearest year same month scaled by ratio of available months
            ny = min(others.index, key=lambda z: abs(z-y))
            C = others.loc[ny, m] * avail.sum()/others.loc[ny, avail.index].sum()
            # D: neighbour mean
            nb = [comp.loc[y, k] for k in (m-1, m+1) if 1 <= k <= 12]
            D = np.mean(nb)
            # E: share from previous year only
            if y-1 in others.index:
                E = others.loc[y-1, m] * avail.sum()/others.loc[y-1, avail.index].sum()
            else: E = C
            # F: sales-ratio: mwh per t sold this year (other months) x t sold this month
            try:
                st = np.array([sales.get((s, y, k), np.nan) for k in range(1, 13)])
                if np.isnan(st).any() or st.sum() == 0: raise KeyError
                r = avail.sum() / st[[k-1 for k in avail.index]].sum()
                F = r * st[m-1]
            except Exception:
                F = np.nan
            res.append(dict(site=s, carrier=c, y=y, m=m, true=true, A=A, B=B, C=C, D=D, E=E, F=F))
r = pd.DataFrame(res)
for k in 'ABCDEF':
    r[k+'_ape'] = (r[k]/r.true-1).abs()
print(r[[k+'_ape' for k in 'ABCDEF']].describe().round(4))
print(r.groupby(['site','carrier'])[[k+'_ape' for k in 'ABCDEF']].median().round(4))
