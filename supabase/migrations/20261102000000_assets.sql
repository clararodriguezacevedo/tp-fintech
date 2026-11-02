-- Every asset IOL offers in our categories, refreshed daily from its panels (app.universe).
create table assets (
  ticker text primary key,
  name text not null,
  category text not null check (category in ('acciones', 'cedears', 'bonos')),
  leader boolean not null default false,  -- in the Merval leaders panel
  sovereign boolean not null default false,  -- in the sovereign dollar bonds panel
  last_price numeric,
  updated_at timestamptz not null default now()
);
alter table assets enable row level security;
