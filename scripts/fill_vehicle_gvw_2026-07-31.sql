-- Gross vehicle weight for the 32 box trucks, from "DS XE VA TAI XE.xlsx",
-- column KLTB (khối lượng toàn bộ = gross vehicle weight), tonnes -> kg.
--
-- Verified before generating, against routing_system.db:
--   * KÍCH THƯỚC in the sheet matches container_configs cargo dimensions for
--     all 32 rows, confirming that column is the CARGO BOX and not the vehicle
--     envelope -- it is not usable for routing restrictions.
--   * TT THỰC matches payload_kg for all 32 rows.
--   * KLTB exceeds payload on every row, by 1.94-7.78 t of kerb weight, which
--     is what makes it gross rather than payload or kerb.
--
-- NOT set here, because the spreadsheet does not contain them:
--   overall_length_mm, overall_width_mm, overall_height_mm, axle_load_kg.
--   Routing continues to use vehicle-type estimates for those, and the
--   dashboard will keep reporting the source as "mixed".
--
-- The 4 container tractors (50H-06136, 51D-48353, 51C-92980, 51C-72095) carry
-- no dimensions or weights in the sheet at all and are untouched.

BEGIN TRANSACTION;

UPDATE vehicles SET gross_weight_kg = 2820, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-93571';  -- 1.5 Tons, was estimated 3490
UPDATE vehicles SET gross_weight_kg = 3605, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-93997';  -- 1.5 Tons, was estimated 3490
UPDATE vehicles SET gross_weight_kg = 3605, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50E-18820';  -- 1.5 Tons, was estimated 3490
UPDATE vehicles SET gross_weight_kg = 4045, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-94382';  -- 1.5 Tons, was estimated 3490
UPDATE vehicles SET gross_weight_kg = 4980, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-36908';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4980, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-93963';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4980, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-94275';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4980, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-93016';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4980, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-79090';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4980, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-94043';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4980, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-94819';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4995, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-79791';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4995, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50E-19793';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4700, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '51D-08660';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4860, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-94524';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4860, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-93915';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4860, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-80142';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4860, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-79107';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 5675, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-80292';  -- 2.5 Tons, was estimated 4990
UPDATE vehicles SET gross_weight_kg = 4995, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50E-19424';  -- 5 Tons, was estimated 8500
UPDATE vehicles SET gross_weight_kg = 8555, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-79744';  -- 5 Tons, was estimated 8500
UPDATE vehicles SET gross_weight_kg = 9340, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-93416';  -- 5 Tons, was estimated 8500
UPDATE vehicles SET gross_weight_kg = 11430, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50E-18463';  -- 5 Tons, was estimated 8500
UPDATE vehicles SET gross_weight_kg = 11370, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-79601';  -- 5 Tons, was estimated 8500
UPDATE vehicles SET gross_weight_kg = 13695, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-80087';  -- 8 Tons, was estimated 15000
UPDATE vehicles SET gross_weight_kg = 13695, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-94776';  -- 8 Tons, was estimated 15000
UPDATE vehicles SET gross_weight_kg = 15110, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '51C-78712';  -- 9 Tons, was estimated 16000
UPDATE vehicles SET gross_weight_kg = 15110, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50F-02247';  -- 9 Tons, was estimated 16000
UPDATE vehicles SET gross_weight_kg = 14780, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-11447';  -- 10 Tons, was estimated 17500
UPDATE vehicles SET gross_weight_kg = 14780, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-11187';  -- 10 Tons, was estimated 17500
UPDATE vehicles SET gross_weight_kg = 15000, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-09491';  -- 10 Tons, was estimated 17500
UPDATE vehicles SET gross_weight_kg = 15000, updated_at = CURRENT_TIMESTAMP WHERE plate_number = '50H-09473';  -- 10 Tons, was estimated 17500

-- Every row above must report changes = 1.
SELECT plate_number, gross_weight_kg FROM vehicles
 WHERE gross_weight_kg IS NOT NULL ORDER BY plate_number;

COMMIT;
