# Organic-soil emissions from the soil map, not from farmer self-reports

Drained organic soils emit about 29 t CO2/ha/yr, 30 to 50 times a mineral-soil pea field (`docs/APETIT_DATA_RECONCILIATION.md`, "Soil and land-use change"). Farmers can misreport mineral soil for peat fields (`START_HERE.md`, "What makes this data realistic"). For every farm, crop and year, our farm footprint therefore uses the **organic share** of the crop's declared parcel area (`parcels.soil_class_soilmap` × `parcel_crop_history`), whatever the survey says. This is a method choice, applied to all farms, not a per-record correction. The provided `farm_calculator.farm_footprint_per_ha` takes a yes/no `organic_soil` per survey row, so we apply the organic-soil term in proportion to area share instead. `soil_misreport` issues are still raised for A1 where the share is ≥ 30 % and the survey says "Mineral soil" (`docs/TASKS_AND_SCORING.md`, A1).

## Consequences

- The soil map is only about 88 % accurate (`docs/DATA_DICTIONARY.md`, `parcels.csv`), so organic-soil emissions carry that uncertainty. The pipeline description must say so.
- Our footprints will differ, on purpose, from `current_calculator_footprints.csv`, which assumes mineral soil. The dashboard can show the gap.
