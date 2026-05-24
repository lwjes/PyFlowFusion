import copy
import importlib.util
import os
from dataclasses import dataclass
from functools import lru_cache


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'configs', 'default.py')


@dataclass(frozen=True)
class PathsConfig:
    project_root: str
    tmp_queue_dir: str
    py_seeds_dir: str
    py_deps_dir: str
    py_fused_dir: str
    bugs_dir: str
    fixme_dir: str
    knowledge_dir: str


@dataclass(frozen=True)
class CPythonConfig:
    source_root: str
    fuzz_python_bin: str
    cov_python_bin: str
    cov_build_root: str


@dataclass(frozen=True)
class RuntimeConfig:
    stop_after: int
    mutation: bool
    apifuzz: bool
    ini: bool
    case_timeout: int
    pending_batch_size: int
    pending_max_tmp: int
    pending_timeout: int


@dataclass(frozen=True)
class CoverageConfig:
    interval: int
    csv_path: str
    phase: str
    gcovr_root: str


@dataclass(frozen=True)
class FlowFusionConfig:
    config_path: str
    paths: PathsConfig
    cpython: CPythonConfig
    runtime: RuntimeConfig
    coverage: CoverageConfig


def _load_config_module(config_path):
    module_name = f'flowfusion_user_config_{abs(hash(config_path))}'
    spec = importlib.util.spec_from_file_location(module_name, config_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f'Unable to load FlowFusion config from {config_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = getattr(module, 'CONFIG', None)
    if not isinstance(config, dict):
        raise SystemExit(f'FlowFusion config {config_path} must define a CONFIG dict')
    return config


def _deep_merge(base, override):
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _resolve_config_path(config_path):
    if not config_path:
        return DEFAULT_CONFIG_PATH
    if os.path.isabs(config_path):
        return config_path
    return os.path.abspath(os.path.join(PROJECT_ROOT, config_path))


def _resolve_path(path_value, base_dir, *, allow_empty=False):
    if path_value in {None, ''}:
        return '' if allow_empty else base_dir
    if os.path.isabs(path_value):
        return os.path.abspath(path_value)
    return os.path.abspath(os.path.join(base_dir, path_value))


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _build_config(config_path, raw_config):
    raw_paths = raw_config.get('paths', {})
    project_root = _resolve_path(raw_paths.get('project_root', PROJECT_ROOT), os.path.dirname(config_path))
    paths = PathsConfig(
        project_root=project_root,
        tmp_queue_dir=_resolve_path(raw_paths.get('tmp_queue_dir', '/tmp'), project_root),
        py_seeds_dir=_resolve_path(raw_paths.get('py_seeds_dir', 'py_seeds'), project_root),
        py_deps_dir=_resolve_path(raw_paths.get('py_deps_dir', 'py_deps'), project_root),
        py_fused_dir=_resolve_path(raw_paths.get('py_fused_dir', 'py_fused'), project_root),
        bugs_dir=_resolve_path(raw_paths.get('bugs_dir', 'bugs'), project_root),
        fixme_dir=_resolve_path(raw_paths.get('fixme_dir', 'fixme'), project_root),
        knowledge_dir=_resolve_path(raw_paths.get('knowledge_dir', 'knowledges'), project_root),
    )

    raw_cpython = raw_config.get('cpython', {})
    cpython = CPythonConfig(
        source_root=_resolve_path(raw_cpython.get('source_root', ''), project_root),
        fuzz_python_bin=_resolve_path(raw_cpython.get('fuzz_python_bin', ''), project_root),
        cov_python_bin=_resolve_path(raw_cpython.get('cov_python_bin', ''), project_root),
        cov_build_root=_resolve_path(raw_cpython.get('cov_build_root', ''), project_root),
    )

    raw_runtime = raw_config.get('runtime', {})
    runtime = RuntimeConfig(
        stop_after=int(raw_runtime.get('stop_after', -1)),
        mutation=_as_bool(raw_runtime.get('mutation', True)),
        apifuzz=_as_bool(raw_runtime.get('apifuzz', False)),
        ini=_as_bool(raw_runtime.get('ini', False)),
        case_timeout=max(1, int(raw_runtime.get('case_timeout', 30))),
        pending_batch_size=max(0, int(raw_runtime.get('pending_batch_size', 0))),
        pending_max_tmp=max(0, int(raw_runtime.get('pending_max_tmp', 0))),
        pending_timeout=max(0, int(raw_runtime.get('pending_timeout', 0))),
    )

    raw_coverage = raw_config.get('coverage', {})
    coverage = CoverageConfig(
        interval=max(0, int(raw_coverage.get('interval', 3600))),
        csv_path=_resolve_path(raw_coverage.get('csv_path', ''), project_root, allow_empty=True),
        phase=str(raw_coverage.get('phase', '')),
        gcovr_root=_resolve_path(
            raw_coverage.get('gcovr_root', cpython.source_root),
            project_root,
        ),
    )

    return FlowFusionConfig(
        config_path=config_path,
        paths=paths,
        cpython=cpython,
        runtime=runtime,
        coverage=coverage,
    )


@lru_cache(maxsize=None)
def load_config(config_path=None):
    resolved_path = _resolve_config_path(config_path or os.getenv('FLOWFUSION_CONFIG', ''))
    if not os.path.isfile(resolved_path):
        raise SystemExit(f'FlowFusion config file not found: {resolved_path}')

    default_config = _load_config_module(DEFAULT_CONFIG_PATH)
    if resolved_path == DEFAULT_CONFIG_PATH:
        merged_config = default_config
    else:
        override_config = _load_config_module(resolved_path)
        merged_config = _deep_merge(default_config, override_config)

    return _build_config(resolved_path, merged_config)
