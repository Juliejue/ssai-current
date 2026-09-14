-- 哪一环对/错（FR-09 / SP-4）。冷启动 L0 数据里最有价值的一列：
-- 它回答的是「推荐依据对不对」，而不是「这个地方好不好」。
ALTER TABLE visit_outcomes
    ADD COLUMN IF NOT EXISTS mismatch_stage text NOT NULL DEFAULT 'none';

ALTER TABLE visit_outcomes
    DROP CONSTRAINT IF EXISTS visit_outcomes_mismatch_stage_check;

ALTER TABLE visit_outcomes
    ADD CONSTRAINT visit_outcomes_mismatch_stage_check
    CHECK (mismatch_stage IN ('none', 'state', 'need', 'constraint', 'place'));

CREATE INDEX IF NOT EXISTS visit_outcomes_mismatch_stage_idx
    ON visit_outcomes (mismatch_stage)
    WHERE mismatch_stage <> 'none';
