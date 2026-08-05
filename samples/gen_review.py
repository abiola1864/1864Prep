"""Run the general cleaning path on a deliberately generic file and emit the
two verification views (column overview + spot-check pool) as JSON."""
import json
import random

import pandas as pd

from engine.pipeline import run_plan
from engine.profile import profile_dataframe, profile_to_plan
from engine.review import column_overview, spotcheck

random.seed(5)

plans = ['basic', 'Basic', 'BASIC', 'premium', 'Premium', 'Premuim', 'enterprise', 'Enterprise', 'ENT']
status = ['active', 'Active', 'inactive', 'Inactive', 'ACTIVE']
depts = ['Sales', 'sales', 'Marketing', 'marketing', 'Enginering', 'Engineering', 'Suport', 'Support', 'HR', 'hr']


def mk():
    return {
        'record_id': f'REC{random.randint(100000, 999999)}',
        'full_name': random.choice(['ADA LOVELACE', 'alan turing', 'Grace Hopper',
                                     'KATHERINE JOHNSON', 'john von neumann', 'Ada L.']),
        'email': random.choice(['ADA@X.IO', 'turing@mail.com', 'grace@nav.mil',
                                'not-an-email', 'k.johnson@nasa.gov']),
        'signup_date': random.choice(['2025-06-01', '6/1/2025', '01/06/2025', '2025/6/1', 'bad-date']),
        'plan_tier': random.choice(plans),
        'status': random.choice(status),
        'department': random.choice(depts),
        'monthly_spend': random.choice(['$1,200.50', '2300', '$980', '1,000', 'N/A']),
        'seats': str(random.choice([1, 5, 12, 50, 3])),
    }


def main():
    df = pd.DataFrame([mk() for _ in range(400)])
    profs = profile_dataframe(df)
    plan = profile_to_plan(profs, 'generic_auto')
    types = {p.column: p.semantic_type for p in profs}
    cleaned, report, _ = run_plan(df, plan, 'generic')
    flags = {c['source_column']: c.get('flagged', 0) for c in report.columns}

    overview = column_overview(df, cleaned, types, flags)
    pool = spotcheck(df, cleaned, pool_size=60, seed=5)

    print('COLUMN OVERVIEW (before -> after):')
    for c in overview:
        eg = c['examples'][:1]
        print(f"  {c['column']:<15} read_as={c['read_as']:<12} changed={c['n_changed']:>3} "
              f"flagged={c['n_flagged']:>3}  e.g. {eg}")
    print(f"\nSpot-check pool: {len(pool['records'])} random records across {len(pool['columns'])} columns")

    data = {'overview': overview, 'pool': pool,
            'meta': {'rows': len(df), 'cols': len(df.columns), 'plan': 'generic_auto'}}
    json.dump(data, open('/tmp/review_data.json', 'w'))
    print('wrote /tmp/review_data.json')


if __name__ == '__main__':
    main()
