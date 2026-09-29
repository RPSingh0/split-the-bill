create type bill_status as enum ('open', 'done', 'cancelled');
create type charge_kind as enum ('tax', 'service_charge', 'discount', 'round_off', 'other');

create table users (
  id            uuid primary key default gen_random_uuid(),
  username      text not null unique check (username ~ '^[a-z0-9_]{3,30}$'),
  password_hash text not null,
  created_at    timestamptz not null default now()
);

create table bills (
  id             uuid primary key default gen_random_uuid(),
  slug           text not null unique,
  owner_id       uuid not null references users(id),
  status         bill_status not null default 'open',
  merchant       text,
  bill_date      date,
  currency       text not null default 'INR',
  subtotal_paise bigint not null,
  total_paise    bigint not null check (total_paise > 0),
  tip_paise      bigint not null default 0 check (tip_paise >= 0),
  tip_percent    numeric(5,2),
  version        integer not null default 1,
  created_at     timestamptz not null default now(),
  closed_at      timestamptz
);
create index bills_owner_created_idx on bills (owner_id, created_at desc);

create table bill_items (
  id               uuid primary key default gen_random_uuid(),
  bill_id          uuid not null references bills(id) on delete cascade,
  position         integer not null,
  name             text not null,
  quantity         numeric(10,3) not null check (quantity > 0),
  unit_price_paise bigint,
  line_total_paise bigint not null check (line_total_paise >= 0)
);
create index bill_items_bill_idx on bill_items (bill_id);

create table bill_charges (
  id           uuid primary key default gen_random_uuid(),
  bill_id      uuid not null references bills(id) on delete cascade,
  position     integer not null,
  label        text not null,
  kind         charge_kind not null,
  rate_percent numeric(6,3),
  amount_paise bigint not null
);
create index bill_charges_bill_idx on bill_charges (bill_id);

create table participants (
  id           uuid primary key default gen_random_uuid(),
  bill_id      uuid not null references bills(id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 30),
  name_key     text not null,
  user_id      uuid references users(id),
  joined_at    timestamptz not null default now(),
  unique (bill_id, name_key)
);

create table claims (
  item_id        uuid not null references bill_items(id) on delete cascade,
  participant_id uuid not null references participants(id) on delete cascade,
  units          integer not null default 1 check (units >= 1),
  updated_at     timestamptz not null default now(),
  primary key (item_id, participant_id)
);
create index claims_participant_idx on claims (participant_id);

alter table users        enable row level security;
alter table bills        enable row level security;
alter table bill_items   enable row level security;
alter table bill_charges enable row level security;
alter table participants enable row level security;
alter table claims       enable row level security;
