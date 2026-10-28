-- The user's investor profile (CNV suitability). IOL's own test result wins when there is one;
-- otherwise the profile the user declared in the app. Single row.
create table investor_profile (
  id smallint primary key default 1 check (id = 1),
  declared text check (declared in ('conservador', 'moderado', 'arriesgado')),
  iol text,  -- as IOL reports it ("Conservador", ...), empty while its test is pending
  iol_test_pending boolean,
  iol_checked_at timestamptz,
  updated_at timestamptz not null default now()
);
alter table investor_profile enable row level security;
insert into investor_profile (id) values (1);

-- Asset kinds from IOL (ACCIONES, CEDEARS, TIT. PUBLICOS...), cached: they don't change.
create table asset_types (
  ticker text primary key,
  asset_type text not null,
  fetched_at timestamptz not null default now()
);
alter table asset_types enable row level security;
