-- Finance Foundation v1 structured schema

CREATE TABLE IF NOT EXISTS financial_profile (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    monthly_salary NUMERIC(12,2),
    monthly_rent NUMERIC(12,2),
    currency TEXT DEFAULT 'EUR',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS financial_commitments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id BIGINT NOT NULL,
    commitment_type TEXT NOT NULL,
    name TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency TEXT DEFAULT 'EUR',
    frequency TEXT DEFAULT 'monthly',
    due_day INTEGER,
    status TEXT DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS financial_goals (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    target_amount NUMERIC(12,2) NOT NULL,
    currency TEXT DEFAULT 'EUR',
    target_date DATE,
    monthly_contribution NUMERIC(12,2),
    status TEXT DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS financial_plans (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id BIGINT NOT NULL,
    plan_type TEXT DEFAULT 'planned_expense',
    title TEXT NOT NULL,
    planned_amount NUMERIC(12,2) NOT NULL,
    currency TEXT DEFAULT 'EUR',
    planned_month TEXT,
    expected_date DATE,
    status TEXT DEFAULT 'planned',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_financial_commitments_user_id ON financial_commitments (user_id);
CREATE INDEX IF NOT EXISTS idx_financial_goals_user_id ON financial_goals (user_id);
CREATE INDEX IF NOT EXISTS idx_financial_plans_user_id ON financial_plans (user_id);
