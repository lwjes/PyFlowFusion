import ast
import base64
import json


SEED_IR_VERSION = 1
SECTION_FIELD_MAP = {
    'prelude': 'prelude',
    'helpers': 'helpers',
    'configuration': 'configuration',
    'body': 'phpcode',
}
SECTION_NODE_KEY_MAP = {
    'prelude': 'prelude_nodes',
    'helpers': 'helper_nodes',
    'configuration': 'configuration_nodes',
    'body': 'body_nodes',
}


def _encode_scalar(value):
    if value is Ellipsis:
        return {'_scalar': 'ellipsis'}
    if isinstance(value, bytes):
        return {'_scalar': 'bytes', 'value': base64.b64encode(value).decode('ascii')}
    if isinstance(value, complex):
        return {'_scalar': 'complex', 'real': value.real, 'imag': value.imag}
    if isinstance(value, tuple):
        return {'_scalar': 'tuple', 'items': [_encode_ast(item) for item in value]}
    if isinstance(value, set):
        return {'_scalar': 'set', 'items': [_encode_ast(item) for item in value]}
    if isinstance(value, frozenset):
        return {'_scalar': 'frozenset', 'items': [_encode_ast(item) for item in value]}
    return value


def _decode_scalar(value):
    if not isinstance(value, dict) or '_scalar' not in value:
        return value

    scalar_type = value['_scalar']
    if scalar_type == 'ellipsis':
        return Ellipsis
    if scalar_type == 'bytes':
        return base64.b64decode(value['value'].encode('ascii'))
    if scalar_type == 'complex':
        return complex(value['real'], value['imag'])
    if scalar_type == 'tuple':
        return tuple(_decode_ast(item) for item in value['items'])
    if scalar_type == 'set':
        return set(_decode_ast(item) for item in value['items'])
    if scalar_type == 'frozenset':
        return frozenset(_decode_ast(item) for item in value['items'])
    return value


def _encode_ast(value):
    if isinstance(value, ast.AST):
        encoded = {'_type': type(value).__name__}
        for field in value._fields:
            encoded[field] = _encode_ast(getattr(value, field))
        return encoded
    if isinstance(value, list):
        return [_encode_ast(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode_ast(item) for key, item in value.items()}
    return _encode_scalar(value)


def _decode_ast(value):
    if isinstance(value, list):
        return [_decode_ast(item) for item in value]
    if isinstance(value, dict):
        if '_type' in value:
            node_cls = getattr(ast, value['_type'])
            kwargs = {
                key: _decode_ast(item)
                for key, item in value.items()
                if key != '_type'
            }
            return node_cls(**kwargs)
        return _decode_scalar({key: _decode_ast(item) for key, item in value.items()})
    return value


def _module_from_body(body):
    return ast.Module(body=list(body or []), type_ignores=[])


def build_seed_ir(
    *,
    prelude_nodes,
    helper_nodes,
    configuration_nodes,
    body_nodes,
    decorator_nodes,
    base_names,
):
    return {
        'version': SEED_IR_VERSION,
        'prelude_nodes': _encode_ast(list(prelude_nodes or [])),
        'helper_nodes': _encode_ast(list(helper_nodes or [])),
        'configuration_nodes': _encode_ast(list(configuration_nodes or [])),
        'body_nodes': _encode_ast(list(body_nodes or [])),
        'decorator_nodes': _encode_ast(list(decorator_nodes or [])),
        'bases': list(base_names or []),
    }


def dumps_seed_ir(seed_ir):
    return json.dumps(seed_ir, sort_keys=True)


def loads_seed_ir(raw_value):
    if not raw_value:
        return None
    try:
        value = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def seed_ir_section_module(seed_ir, section_name):
    if not isinstance(seed_ir, dict):
        return None
    key = SECTION_NODE_KEY_MAP.get(section_name)
    if not key or key not in seed_ir:
        return None
    body = _decode_ast(seed_ir.get(key) or [])
    module = _module_from_body(body)
    ast.fix_missing_locations(module)
    return module


def seed_ir_decorator_nodes(seed_ir):
    if not isinstance(seed_ir, dict) or 'decorator_nodes' not in seed_ir:
        return None
    nodes = _decode_ast(seed_ir.get('decorator_nodes') or [])
    return list(nodes or [])


def seed_ir_base_names(seed_ir):
    if not isinstance(seed_ir, dict) or 'bases' not in seed_ir:
        return None
    bases = seed_ir.get('bases')
    return list(bases) if isinstance(bases, list) else None


def build_legacy_seed_ir(record):
    def parse_module(text):
        if not text or not text.strip():
            return []
        return ast.parse(text).body

    def parse_decorators(text):
        nodes = []
        for raw in (text or '').splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith('@'):
                line = line[1:].strip()
            try:
                expr = ast.parse(line, mode='eval').body
            except SyntaxError:
                continue
            nodes.append(expr)
        return nodes

    bases = []
    try:
        maybe_bases = ast.literal_eval(record.get('bases') or '[]')
        if isinstance(maybe_bases, list):
            bases = [item for item in maybe_bases if isinstance(item, str)]
    except Exception:
        bases = []

    return build_seed_ir(
        prelude_nodes=parse_module(record.get('prelude', '')),
        helper_nodes=parse_module(record.get('helpers', '')),
        configuration_nodes=parse_module(record.get('configuration', '')),
        body_nodes=parse_module(record.get('phpcode', '')),
        decorator_nodes=parse_decorators(record.get('skipif', '')),
        base_names=bases,
    )
