from app.db import engine_url


def test_plain_postgresql_url_uses_psycopg():
    url = "postgresql://user:secret@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"

    assert engine_url(url) == "postgresql+psycopg://user:secret@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"


def test_psycopg_url_is_unchanged():
    url = "postgresql+psycopg://postgres:postgres@localhost:5432/split_the_bill"

    assert engine_url(url) == url
