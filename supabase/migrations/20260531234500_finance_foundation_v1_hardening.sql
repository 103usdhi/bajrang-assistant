-- Finance Foundation v1 hardening:
-- 1) data-quality constraints
-- 2) stricter access model for sensitive finance tables

-- Service-role only data access for finance tables.
REVOKE ALL PRIVILEGES ON TABLE public.financial_profile FROM authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.financial_commitments FROM authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.financial_goals FROM authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.financial_plans FROM authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.financial_profile TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.financial_commitments TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.financial_goals TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.financial_plans TO service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_commitments_amount_positive_chk'
    ) THEN
        ALTER TABLE public.financial_commitments
            ADD CONSTRAINT financial_commitments_amount_positive_chk
            CHECK (amount > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_goals_target_amount_positive_chk'
    ) THEN
        ALTER TABLE public.financial_goals
            ADD CONSTRAINT financial_goals_target_amount_positive_chk
            CHECK (target_amount > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_goals_monthly_contribution_positive_chk'
    ) THEN
        ALTER TABLE public.financial_goals
            ADD CONSTRAINT financial_goals_monthly_contribution_positive_chk
            CHECK (monthly_contribution IS NULL OR monthly_contribution > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_plans_planned_amount_positive_chk'
    ) THEN
        ALTER TABLE public.financial_plans
            ADD CONSTRAINT financial_plans_planned_amount_positive_chk
            CHECK (planned_amount > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_commitments_due_day_range_chk'
    ) THEN
        ALTER TABLE public.financial_commitments
            ADD CONSTRAINT financial_commitments_due_day_range_chk
            CHECK (due_day IS NULL OR due_day BETWEEN 1 AND 31);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_commitments_status_allowed_chk'
    ) THEN
        ALTER TABLE public.financial_commitments
            ADD CONSTRAINT financial_commitments_status_allowed_chk
            CHECK (status IN ('active', 'completed', 'cancelled'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_goals_status_allowed_chk'
    ) THEN
        ALTER TABLE public.financial_goals
            ADD CONSTRAINT financial_goals_status_allowed_chk
            CHECK (status IN ('active', 'completed', 'cancelled'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_plans_status_allowed_chk'
    ) THEN
        ALTER TABLE public.financial_plans
            ADD CONSTRAINT financial_plans_status_allowed_chk
            CHECK (status IN ('planned', 'completed', 'cancelled'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_commitments_type_allowed_chk'
    ) THEN
        ALTER TABLE public.financial_commitments
            ADD CONSTRAINT financial_commitments_type_allowed_chk
            CHECK (commitment_type IN ('emi_loan', 'recurring_bill'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_plans_type_allowed_chk'
    ) THEN
        ALTER TABLE public.financial_plans
            ADD CONSTRAINT financial_plans_type_allowed_chk
            CHECK (plan_type IN ('planned_expense', 'investment', 'expected_refund', 'expected_income', 'purchase'));
    END IF;
END $$;
