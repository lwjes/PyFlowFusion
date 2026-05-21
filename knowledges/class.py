import json
import os
import sqlite3
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flowfusion.config import load_config


DB_NAME = 'class.db'
DEFAULT_PYTHON = load_config().cpython.fuzz_python_bin
MODULE_CANDIDATES = [
    'builtins',
    'collections',
    'collections.abc',
    'array',
    'heapq',
    'bisect',
    'datetime',
    'decimal',
    'fractions',
    'functools',
    'itertools',
    'pathlib',
    'queue',
    'random',
    're',
    'statistics',
    'string',
    'types',
    'typing',
    'urllib.parse',
]


INTROSPECTION_SCRIPT = r"""
import importlib
import inspect
import json
import types

MODULES = %MODULES%


def safe_signature_param_count(obj):
    try:
        sig = inspect.signature(obj)
    except Exception:
        return 0
    count = 0
    for param in sig.parameters.values():
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            if param.name not in {'self', 'cls'}:
                count += 1
    return count


def collect_class_info(cls):
    attributes = []
    methods = []

    for name in sorted(set(dir(cls))):
        try:
            value = getattr(cls, name)
        except Exception:
            continue

        if callable(value):
            methods.append({
                'name': name,
                'params_count': safe_signature_param_count(value),
            })
        else:
            attributes.append(name)

    return {
        'class_name': f'{cls.__module__}.{cls.__name__}',
        'attributes': attributes,
        'methods': methods,
    }


def main():
    seen = set()
    classes = []

    for module_name in MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj in seen:
                continue
            if getattr(obj, '__module__', '') in {'typing', 'typing_extensions'} and hasattr(obj, '__origin__'):
                continue
            seen.add(obj)
            classes.append(collect_class_info(obj))

    print(json.dumps(classes))


if __name__ == '__main__':
    main()
"""


def resolve_python_bin():
    candidate = DEFAULT_PYTHON
    if candidate and os.path.exists(candidate):
        return candidate
    return sys.executable


def extract_classes_from_cpython():
    python_bin = resolve_python_bin()
    script = INTROSPECTION_SCRIPT.replace('%MODULES%', repr(MODULE_CANDIDATES))
    result = subprocess.run(
        [python_bin, '-c', script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or f'failed to introspect classes with {python_bin}')
    return json.loads(result.stdout)


def create_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT UNIQUE
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            name TEXT,
            FOREIGN KEY (class_id) REFERENCES classes (id)
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            name TEXT,
            params_count INTEGER,
            FOREIGN KEY (class_id) REFERENCES classes (id)
        )
        '''
    )

    cursor.execute('DELETE FROM attributes')
    cursor.execute('DELETE FROM methods')
    cursor.execute('DELETE FROM classes')
    conn.commit()
    return conn


def insert_data(conn, classes):
    cursor = conn.cursor()

    for class_info in classes:
        class_name = class_info['class_name']
        cursor.execute('INSERT OR IGNORE INTO classes (class_name) VALUES (?)', (class_name,))
        cursor.execute('SELECT id FROM classes WHERE class_name = ?', (class_name,))
        class_id = cursor.fetchone()[0]

        for attr_name in class_info.get('attributes', []):
            cursor.execute(
                'INSERT INTO attributes (class_id, name) VALUES (?, ?)',
                (class_id, attr_name),
            )

        for method_info in class_info.get('methods', []):
            cursor.execute(
                'INSERT INTO methods (class_id, name, params_count) VALUES (?, ?, ?)',
                (class_id, method_info['name'], method_info['params_count']),
            )

    conn.commit()


def main():
    classes = extract_classes_from_cpython()
    conn = create_database()
    insert_data(conn, classes)
    conn.close()
    print(f"Data has been successfully imported into '{DB_NAME}' ({len(classes)} classes).")


if __name__ == '__main__':
    main()
