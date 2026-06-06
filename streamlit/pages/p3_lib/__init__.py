"""Page 3 (Investment Planning) — refactored section modules.

The page is structured as a pipeline:
    require_login → init state → upstream gate → read upstream →
    Section 1 (plan context) → Section 2 (bucket config) →
    Section 3 (auto allocation preview) → Section 4 (MC config) →
    Section 5 (MC run) → Section 6 (results).

Each section module exposes `render(ctx)` or returns values that the
orchestrator merges into `ctx` (a plain dict carried across sections).
"""
