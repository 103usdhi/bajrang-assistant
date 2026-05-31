-- Corrective migration: remove anon access from personal finance tables.
-- RLS policies are not currently defined for these tables.

REVOKE ALL PRIVILEGES ON TABLE public.financial_profile FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.financial_commitments FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.financial_goals FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.financial_plans FROM anon;
