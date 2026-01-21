CREATE TABLE IF NOT EXISTS houm_users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    name_key VARCHAR NOT NULL UNIQUE,
    min_price INTEGER,
    max_price INTEGER,
    min_rooms FLOAT,
    max_rooms FLOAT,
    min_area FLOAT,
    max_area FLOAT,
    min_year INTEGER,
    max_year INTEGER,
    max_monthly_fee INTEGER,
    housing_forms JSONB,
    tenure JSONB,
    municipalities JSONB,
    regions JSONB,
    districts JSONB,
    prefer_new_construction BOOLEAN,
    prefer_upcoming BOOLEAN,
    max_coast_distance_m INTEGER,
    max_water_distance_m INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE houm_users
    ADD COLUMN IF NOT EXISTS name VARCHAR,
    ADD COLUMN IF NOT EXISTS name_key VARCHAR,
    ADD COLUMN IF NOT EXISTS min_price INTEGER,
    ADD COLUMN IF NOT EXISTS max_price INTEGER,
    ADD COLUMN IF NOT EXISTS min_rooms FLOAT,
    ADD COLUMN IF NOT EXISTS max_rooms FLOAT,
    ADD COLUMN IF NOT EXISTS min_area FLOAT,
    ADD COLUMN IF NOT EXISTS max_area FLOAT,
    ADD COLUMN IF NOT EXISTS min_year INTEGER,
    ADD COLUMN IF NOT EXISTS max_year INTEGER,
    ADD COLUMN IF NOT EXISTS max_monthly_fee INTEGER,
    ADD COLUMN IF NOT EXISTS housing_forms JSONB,
    ADD COLUMN IF NOT EXISTS tenure JSONB,
    ADD COLUMN IF NOT EXISTS municipalities JSONB,
    ADD COLUMN IF NOT EXISTS regions JSONB,
    ADD COLUMN IF NOT EXISTS districts JSONB,
    ADD COLUMN IF NOT EXISTS prefer_new_construction BOOLEAN,
    ADD COLUMN IF NOT EXISTS prefer_upcoming BOOLEAN,
    ADD COLUMN IF NOT EXISTS max_coast_distance_m INTEGER,
    ADD COLUMN IF NOT EXISTS max_water_distance_m INTEGER,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS houm_users_name_key_idx ON houm_users(name_key);

CREATE TABLE IF NOT EXISTS houm_favorites (
    user_id BIGINT NOT NULL REFERENCES houm_users(id) ON DELETE CASCADE,
    hemnet_id BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, hemnet_id)
);
