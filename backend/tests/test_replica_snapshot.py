from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, JSON, MetaData, String, Table, create_engine, inspect, select
from sqlalchemy.exc import OperationalError



def test_replica_rebuilds_stale_schema_and_preserves_previous_snapshot_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('CMH_SMS_DATABASE_URL', 'sqlite://')
    from app import database, models  # noqa: F401
    metadata = MetaData()
    tokens = Table('queue_tokens', metadata, Column('id', Integer, primary_key=True),
                   Column('custom_fields', JSON), Column('summary_category_source', String))
    source_path = tmp_path / 'primary-test.db'
    source = create_engine(f'sqlite:///{source_path}')
    metadata.create_all(source)
    with source.begin() as conn:
        conn.execute(tokens.insert(), {'id': 1, 'custom_fields': {'custom_ref': 'test'}, 'summary_category_source': 'manual'})
    destination = tmp_path / 'snapshot.db'
    old = create_engine(f'sqlite:///{destination}')
    with old.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE queue_tokens (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('INSERT INTO queue_tokens VALUES (99)')
    old.dispose()
    monkeypatch.setattr(database, 'Base', SimpleNamespace(metadata=metadata))
    def engines(url, **kwargs):
        return create_engine(f'sqlite:///{source_path}') if url.startswith('postgresql') else create_engine(url, **kwargs)
    monkeypatch.setattr(database, 'create_engine', engines)
    url = f'sqlite:///{destination}'
    assert database._ensure_sqlite_replica('postgresql://test/test', url) == url
    result = create_engine(url)
    assert {'custom_fields', 'summary_category_source'} <= {item['name'] for item in inspect(result).get_columns('queue_tokens')}
    with result.connect() as conn:
        assert conn.execute(select(tokens)).one()._mapping['custom_fields'] == {'custom_ref': 'test'}
    result.dispose()
    previous = destination.read_bytes()
    with source.begin() as conn:
        conn.exec_driver_sql('DROP TABLE queue_tokens')
    with pytest.raises(OperationalError):
        database._ensure_sqlite_replica('postgresql://test/test', url)
    assert destination.read_bytes() == previous
    assert not list(tmp_path.glob('snapshot.db.*.tmp'))
    source.dispose()
