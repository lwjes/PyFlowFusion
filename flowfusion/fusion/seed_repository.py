import os
import sqlite3
from collections import OrderedDict
from collections.abc import Mapping

from flowfusion.fusion.seed_ir import build_legacy_seed_ir, loads_seed_ir


_ALL_SEED_FIELDS = (
    'phpcode',
    'variable',
    'dataflow',
    'description',
    'configuration',
    'skipif',
    'extension',
    'language',
    'prelude',
    'helpers',
    'bases',
    'seed_ir',
)
_LIGHTWEIGHT_FIELDS = (
    'description',
    'phpcode',
    'configuration',
    'skipif',
    'prelude',
    'helpers',
)
_LAZY_FETCH_FIELDS = (
    'variable',
    'dataflow',
    'extension',
    'bases',
    'seed_ir',
)
_DEFAULT_FIELD_VALUES = {
    'phpcode': '',
    'variable': '',
    'dataflow': '',
    'description': '',
    'configuration': '',
    'skipif': '',
    'extension': '',
    'language': 'python',
    'prelude': '',
    'helpers': '',
    'bases': '[]',
    'seed_ir': None,
}
_FULL_ROW_CACHE_SIZE = 8
_SEED_IR_CACHE_SIZE = 8


def _remember_lru(cache, key, value, max_size):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > max_size:
        cache.popitem(last=False)


class SeedRecord(Mapping):
    __slots__ = ('_repository', 'rowid', '_initial_data')

    def __init__(self, repository, rowid, initial_data):
        self._repository = repository
        self.rowid = rowid
        self._initial_data = initial_data

    def __getitem__(self, key):
        if key not in _ALL_SEED_FIELDS:
            raise KeyError(key)
        return self._repository.get_value(self.rowid, key, self._initial_data, self)

    def __iter__(self):
        return iter(_ALL_SEED_FIELDS)

    def __len__(self):
        return len(_ALL_SEED_FIELDS)


class SeedRepository:
    def __init__(self, test_root):
        db_path = os.path.join(test_root, 'knowledges', 'seeds.db')
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._cursor = self._conn.cursor()
        self._cursor.execute('PRAGMA table_info(seeds)')
        self._columns = {row[1] for row in self._cursor.fetchall()}
        self._has_prelude = 'prelude' in self._columns
        self._has_helpers = 'helpers' in self._columns
        self._has_bases = 'bases' in self._columns
        self._has_seed_ir = 'seed_ir' in self._columns
        self._full_row_cache = OrderedDict()
        self._seed_ir_cache = OrderedDict()

    def __del__(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def _default_value(self, key):
        return _DEFAULT_FIELD_VALUES.get(key, '')

    def _candidate_select_columns(self):
        columns = ['rowid AS seed_rowid']
        columns.extend(
            field for field in _LIGHTWEIGHT_FIELDS
            if field not in {'prelude', 'helpers'}
        )
        if self._has_prelude:
            columns.append('prelude')
        if self._has_helpers:
            columns.append('helpers')
        return columns

    def _lazy_select_columns(self):
        columns = ['variable', 'dataflow', 'extension']
        if self._has_bases:
            columns.append('bases')
        if self._has_seed_ir:
            columns.append('seed_ir')
        return columns

    def iter_records(self):
        select_columns = self._candidate_select_columns()
        query = (
            f"SELECT {', '.join(select_columns)} "
            "FROM seeds WHERE lower(language) = 'python'"
        )
        self._cursor.execute(query)
        for row in self._cursor:
            initial = {
                'description': row['description'] or '',
                'phpcode': row['phpcode'] or '',
                'configuration': row['configuration'] or '',
                'skipif': row['skipif'] or '',
                'prelude': row['prelude'] if self._has_prelude else '',
                'helpers': row['helpers'] if self._has_helpers else '',
            }
            yield SeedRecord(self, row['seed_rowid'], initial)

    def _fetch_lazy_row(self, rowid):
        cached = self._full_row_cache.get(rowid)
        if cached is not None:
            self._full_row_cache.move_to_end(rowid)
            return cached

        select_columns = self._lazy_select_columns()
        self._cursor.execute(
            f"SELECT {', '.join(select_columns)} FROM seeds WHERE rowid = ?",
            (rowid,),
        )
        row = self._cursor.fetchone()
        if row is None:
            raise KeyError(f'Unknown seed rowid: {rowid}')

        record = {
            'variable': row['variable'] or '',
            'dataflow': row['dataflow'] or '',
            'extension': row['extension'] or '',
            'bases': row['bases'] if self._has_bases else '[]',
            'seed_ir': row['seed_ir'] if self._has_seed_ir else None,
        }
        _remember_lru(self._full_row_cache, rowid, record, _FULL_ROW_CACHE_SIZE)
        return record

    def _load_seed_ir(self, rowid, initial_data, record):
        cached = self._seed_ir_cache.get(rowid)
        if cached is not None:
            self._seed_ir_cache.move_to_end(rowid)
            return cached

        lazy_row = self._fetch_lazy_row(rowid)
        seed_ir = loads_seed_ir(lazy_row.get('seed_ir')) if self._has_seed_ir else None
        if seed_ir is None:
            seed_ir = build_legacy_seed_ir(record)

        # Drop the raw JSON payload once decoded so the cache only keeps the parsed form.
        lazy_row['seed_ir'] = None
        _remember_lru(self._seed_ir_cache, rowid, seed_ir, _SEED_IR_CACHE_SIZE)
        return seed_ir

    def get_value(self, rowid, key, initial_data, record):
        if key in initial_data:
            return initial_data[key]
        if key == 'language':
            return 'python'
        if key == 'seed_ir':
            return self._load_seed_ir(rowid, initial_data, record)
        if key == 'prelude' and not self._has_prelude:
            return ''
        if key == 'helpers' and not self._has_helpers:
            return ''
        if key == 'bases' and not self._has_bases:
            return '[]'

        return self._fetch_lazy_row(rowid).get(key, self._default_value(key))


def load_seed_records(test_root):
    repository = SeedRepository(test_root)
    return list(repository.iter_records())
