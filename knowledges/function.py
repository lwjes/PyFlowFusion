import json
import os
import sqlite3
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flowfusion.config import load_config


DB_NAME = 'apis.db'
DEFAULT_PYTHON = load_config().cpython.fuzz_python_bin
MODULE_CANDIDATES = [
    'builtins',
    'array',
    'binascii',
    'cmath',
    'collections',
    'datetime',
    'decimal',
    'functools',
    'hashlib',
    'heapq',
    'itertools',
    'json',
    'math',
    'operator',
    'os',
    'pathlib',
    'pickle',
    'queue',
    'random',
    're',
    'sqlite3',
    'statistics',
    'string',
    'subprocess',
    'tempfile',
    'types',
    'typing',
    'unicodedata',
    'urllib.parse',
]


INTROSPECTION_SCRIPT = r"""
import importlib
import inspect
import json
import types

MODULES = %MODULES%


def safe_parameter_info(obj):
    try:
        sig = inspect.signature(obj)
    except Exception:
        return []

    params = []
    for param in sig.parameters.values():
        params.append({
            'name': param.name,
            'type': '' if param.annotation is inspect._empty else repr(param.annotation),
            'is_optional': param.default is not inspect._empty,
            'default_value': None if param.default is inspect._empty else repr(param.default),
            'kind': str(param.kind),
        })
    return params


def function_record(module_name, func_name, obj):
    params = safe_parameter_info(obj)
    positional_count = 0
    for param in params:
        if param['kind'] in {
            'POSITIONAL_ONLY',
            'POSITIONAL_OR_KEYWORD',
        }:
            positional_count += 1

    return {
        'name': f'{module_name}.{func_name}' if module_name != 'builtins' else func_name,
        'num_params': positional_count,
        'params': params,
    }


def main():
    seen = set()
    functions = []

    for module_name in MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj):
                continue
            if not callable(obj):
                continue
            key = (module_name, name)
            if key in seen:
                continue
            seen.add(key)
            functions.append(function_record(module_name, name, obj))

    print(json.dumps(functions))


if __name__ == '__main__':
    main()
"""


def load_builtin_patterns():
    return [
        {
            'id': 'py-code-injection-eval',
            'category': 'code-injection',
            'sink': 'eval',
            'description': 'Untrusted input reaches eval().',
            'severity': 'high',
            'source_examples': 'input,sys.argv,os.environ,flask.request.args',
        },
        {
            'id': 'py-code-injection-exec',
            'category': 'code-injection',
            'sink': 'exec',
            'description': 'Untrusted input reaches exec().',
            'severity': 'high',
            'source_examples': 'input,sys.argv,os.environ,flask.request.form',
        },
        {
            'id': 'py-command-injection-os-system',
            'category': 'command-injection',
            'sink': 'os.system',
            'description': 'User-controlled command reaches os.system().',
            'severity': 'high',
            'source_examples': 'input,sys.argv,request.args',
        },
        {
            'id': 'py-deserialization-pickle-loads',
            'category': 'deserialization',
            'sink': 'pickle.loads',
            'description': 'Untrusted data is deserialized by pickle.loads().',
            'severity': 'high',
            'source_examples': 'socket.recv,request.data,base64.b64decode',
        },
        {
            'id': 'py-path-traversal-open',
            'category': 'path-traversal',
            'sink': 'open',
            'description': 'Untrusted path reaches open() without validation.',
            'severity': 'medium',
            'source_examples': 'input,request.args.get,sys.argv',
        },
        {
            'id': 'py-ssti-jinja2-template',
            'category': 'template-injection',
            'sink': 'jinja2.Template',
            'description': 'User-controlled template string rendered directly.',
            'severity': 'high',
            'source_examples': 'request.args,request.form',
        },
    ]


def resolve_python_bin():
    candidate = DEFAULT_PYTHON
    if candidate and os.path.exists(candidate):
        return candidate
    return sys.executable


def extract_functions_from_cpython():
    python_bin = resolve_python_bin()
    script = INTROSPECTION_SCRIPT.replace('%MODULES%', repr(MODULE_CANDIDATES))
    result = subprocess.run(
        [python_bin, '-c', script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or f'failed to introspect functions with {python_bin}')
    return json.loads(result.stdout)


def create_database(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            num_params INTEGER NOT NULL
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            function_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT,
            is_optional INTEGER NOT NULL,
            default_value TEXT,
            FOREIGN KEY (function_id) REFERENCES functions (id)
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS patterns (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            sink TEXT NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL,
            source_examples TEXT NOT NULL
        )
        '''
    )

    cursor.execute('DELETE FROM parameters')
    cursor.execute('DELETE FROM functions')
    cursor.execute('DELETE FROM patterns')
    conn.commit()
    return conn


def insert_data(conn, data):
    cursor = conn.cursor()

    for function in data:
        cursor.execute(
            '''
            INSERT INTO functions (name, num_params)
            VALUES (?, ?)
            ''',
            (function['name'], function.get('num_params', 0)),
        )
        function_id = cursor.lastrowid

        for param in function.get('params', []):
            default_value = param.get('default_value')
            if default_value is not None:
                default_value = str(default_value)

            cursor.execute(
                '''
                INSERT INTO parameters (function_id, name, type, is_optional, default_value)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    function_id,
                    param.get('name', ''),
                    param.get('type', ''),
                    1 if param.get('is_optional') else 0,
                    default_value,
                ),
            )

    conn.commit()


def insert_patterns(conn, patterns):
    cursor = conn.cursor()
    for row in patterns:
        cursor.execute(
            '''
            INSERT OR REPLACE INTO patterns (id, category, sink, description, severity, source_examples)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                row.get('id'),
                row.get('category', 'unknown'),
                row.get('sink', ''),
                row.get('description', ''),
                row.get('severity', 'medium'),
                row.get('source_examples', ''),
            ),
        )
    conn.commit()


def main():
    data = extract_functions_from_cpython()
    patterns = load_builtin_patterns()

    conn = create_database(DB_NAME)
    insert_data(conn, data)
    insert_patterns(conn, patterns)
    conn.close()
    print(f"Data has been successfully imported into '{DB_NAME}' ({len(data)} functions + patterns).")


if __name__ == '__main__':
    main()
