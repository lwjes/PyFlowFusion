import os
import sqlite3
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flowfusion.config import load_config


def run_python_script(script_name, config):
    script_path = os.path.join(config.paths.knowledge_dir, script_name)
    env = os.environ.copy()
    env['FLOWFUSION_CONFIG'] = config.config_path
    result = subprocess.run([sys.executable, script_path], cwd=config.paths.knowledge_dir, env=env)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def fetch_scalar(config, db_name, query):
    db_path = os.path.join(config.paths.knowledge_dir, db_name)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchone()[0]


def print_knowledge_stats(config):
    class_count = fetch_scalar(config, 'class.db', 'SELECT COUNT(*) FROM classes')
    method_count = fetch_scalar(config, 'class.db', 'SELECT COUNT(*) FROM methods')
    attribute_count = fetch_scalar(config, 'class.db', 'SELECT COUNT(*) FROM attributes')

    function_count = fetch_scalar(config, 'apis.db', 'SELECT COUNT(*) FROM functions')
    parameter_count = fetch_scalar(config, 'apis.db', 'SELECT COUNT(*) FROM parameters')
    pattern_count = fetch_scalar(config, 'apis.db', 'SELECT COUNT(*) FROM patterns')

    print(
        'class.db stats: '
        f'classes={class_count}, methods={method_count}, attributes={attribute_count}'
    )
    print(
        'apis.db stats: '
        f'functions={function_count}, parameters={parameter_count}, patterns={pattern_count}'
    )


def validate_seed_database(config):
    seed_count = fetch_scalar(
        config,
        'seeds.db',
        "SELECT COUNT(*) FROM seeds WHERE lower(language) = 'python'",
    )
    if seed_count == 0:
        print('warning: seeds.db contains 0 Python seeds')
    else:
        print(f'seeds.db contains {seed_count} Python seed(s)')


def main():
    config = load_config()
    print('building Python knowledge databases')
    run_python_script('function.py', config)
    run_python_script('class.py', config)
    run_python_script('seed-preprocessing.py', config)
    print_knowledge_stats(config)
    validate_seed_database(config)


if __name__ == '__main__':
    main()
