-- 在场证明 L1（FR-08）。存的是结论和停留时长，不存任何坐标：
-- 围栏判定在浏览器里完成，用户的经纬度一次都没有离开设备。
ALTER TABLE visit_outcomes
    ADD COLUMN IF NOT EXISTS presence_level text NOT NULL DEFAULT 'self_reported';

ALTER TABLE visit_outcomes
    ADD COLUMN IF NOT EXISTS dwell_minutes integer NOT NULL DEFAULT 0;

ALTER TABLE visit_outcomes
    DROP CONSTRAINT IF EXISTS visit_outcomes_presence_level_check;

ALTER TABLE visit_outcomes
    ADD CONSTRAINT visit_outcomes_presence_level_check
    CHECK (presence_level IN ('geofence_dwell', 'dwell_only', 'self_reported'));

ALTER TABLE visit_outcomes
    DROP CONSTRAINT IF EXISTS visit_outcomes_dwell_minutes_check;

ALTER TABLE visit_outcomes
    ADD CONSTRAINT visit_outcomes_dwell_minutes_check
    CHECK (dwell_minutes BETWEEN 0 AND 1440);

-- 聚合空间档案时只应该采信核验过的到访（FR-10 奖励与可信度脱钩）。
CREATE INDEX IF NOT EXISTS visit_outcomes_presence_idx
    ON visit_outcomes (place_id, presence_level, created_at DESC);
