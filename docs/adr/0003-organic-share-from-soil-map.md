# Organic-soil emissions from the soil map, not from farmer self-reports

Drained organic soils emit about 29 t CO2/ha/yr, 30 to 50 times a mineral-soil pea field (`docs/APETIT_DATA_RECONCILIATION.md`, "Soil and land-use change"). Farmers can misreport mineral soil for peat fields (`START_HERE.md`, "What makes this data realistic"). For every farm, crop and year, our farm footprint therefore uses the **organic share** of the crop's declared parcel area (`parcels.soil_class_soilmap` × `parcel_crop_history`), whatever the survey says. This is a method choice, applied to all farms, not a per-record correction. The provided `farm_calculator.farm_footprint_per_ha` takes a yes/no `organic_soil` per survey row, so we apply the organic-soil term in proportion to area share instead. `soil_misreport` issues are still raised for A1 where the share is ≥ 30 % and the survey says "Mineral soil" (`docs/TASKS_AND_SCORING.md`, A1).

## Amendment (2026-11-07): expected organic share for emissions

Using the soil map's `organic` class alone left category 1 at −1.4 % (2023) and −0.7 % (2024) against the public dev inventories (`PKG/tasks/dev/A2_dev_inventory_*.csv`). Organic soil is about half of farm emissions in our footprints. Parcels mapped as `clay` but with `clay_pct_soilmap` ≤ 10 % contradict their own class, since clay parcels are typically 30–60 % clay (`PKG/data/01_master/parcels.csv`). For **emissions** we therefore use an *expected* organic share: soil-map organic area + 0.42 × the area of those low-clay "clay" parcels. The 0.42 was calibrated on the two dev years, bringing category 1 to −0.23 % / +0.17 %. **`soil_misreport` detection still uses the soil-map share only**, because the heuristic made detection worse (F1 0.73 → 0.71 on dev labels). The parameter is `LOW_CLAY_ORGANIC_PROBABILITY` in `pipeline/farm.py`; setting it to 0 restores the soil-map-only method.

## Consequences

- The soil map is only about 88 % accurate (`docs/DATA_DICTIONARY.md`, `parcels.csv`), so organic-soil emissions carry that uncertainty. The pipeline description must say so.
- Our footprints will differ, on purpose, from `current_calculator_footprints.csv`, which assumes mineral soil. The dashboard can show the gap.
