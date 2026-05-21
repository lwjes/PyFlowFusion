#!/usr/bin/env python3
import argparse
import ast
import csv
import hashlib
import json
import os
import pathlib
import tokenize


PREFIXES = [
    b"\x00\x01\x00",  # start=eval_input
    b"\x01\x01\x00",  # start=single_input
    b"\x02\x01\x00",  # start=file_input
]


def read_source_text(path):
    try:
        with tokenize.open(path) as handle:
            return handle.read()
    except Exception:
        return None


def snippet_id(source_path, label, content):
    digest = hashlib.sha1(
        (str(source_path) + "\n" + label + "\n" + content).encode("utf-8", "ignore")
    ).hexdigest()[:12]
    stem = source_path.stem
    return f"{stem}__{label}__{digest}"


def to_payload_bytes(text):
    return text.encode("utf-8", "ignore")


def write_seed_variants(seed_dir, base_id, payload, records, source_path, strategy):
    for idx, prefix in enumerate(PREFIXES, start=1):
        out_name = f"{base_id}__p{idx}.seed"
        out_path = seed_dir / out_name
        out_path.write_bytes(prefix + payload)
        records.append(
            {
                "seed_file": str(out_path),
                "source_file": str(source_path),
                "strategy": strategy,
                "payload_bytes": len(payload),
                "seed_bytes": len(prefix) + len(payload),
            }
        )


def collect_class_method_snippets(lines, class_node, class_label):
    if not class_node.body:
        return []

    class_start = class_node.lineno
    first_body_lineno = min(getattr(node, "lineno", class_start + 1) for node in class_node.body)
    class_header = "".join(lines[class_start - 1 : first_body_lineno - 1])
    snippets = []
    for method_idx, child in enumerate(class_node.body, start=1):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = child.lineno
        end = getattr(child, "end_lineno", child.lineno)
        method_segment = "".join(lines[start - 1 : end])
        label = f"{class_label}_m{method_idx}_{child.name}"
        snippets.append((label, class_header + method_segment))
    return snippets


def collect_chunk_fallback_snippets(lines, base_label):
    snippets = []
    window = 220
    step = 160
    for pos in range(0, max(1, len(lines)), step):
        segment = "".join(lines[pos : pos + window])
        if not segment.strip():
            continue
        label = f"{base_label}_chunk{pos}"
        snippets.append((label, segment))
    return snippets


def build_large_file_payloads(path, text, max_payload):
    lines = text.splitlines(keepends=True)
    module = ast.parse(text)

    top_level = [
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if not top_level:
        return []

    first_top_lineno = min(node.lineno for node in top_level)
    prefix = "".join(lines[: max(0, first_top_lineno - 1)])
    if len(to_payload_bytes(prefix)) > (max_payload // 2):
        prefix = ""

    payloads = []
    for node_idx, node in enumerate(top_level, start=1):
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        body = "".join(lines[start - 1 : end])
        base_label = f"top{node_idx}_{type(node).__name__}_{getattr(node, 'name', 'anon')}"

        candidate = (prefix + "\n" + body) if prefix else body
        candidate_bytes = to_payload_bytes(candidate)
        if len(candidate_bytes) <= max_payload:
            payloads.append((base_label, candidate, "top_level"))
            continue

        emitted = False
        if isinstance(node, ast.ClassDef):
            for method_label, method_text in collect_class_method_snippets(lines, node, base_label):
                class_candidate = (prefix + "\n" + method_text) if prefix else method_text
                class_bytes = to_payload_bytes(class_candidate)
                if len(class_bytes) <= max_payload:
                    payloads.append((method_label, class_candidate, "class_method"))
                    emitted = True
            if emitted:
                continue

        for chunk_label, chunk_text in collect_chunk_fallback_snippets(body.splitlines(keepends=True), base_label):
            chunk_candidate = (prefix + "\n" + chunk_text) if prefix else chunk_text
            chunk_bytes = to_payload_bytes(chunk_candidate)
            if len(chunk_bytes) > max_payload:
                continue
            try:
                ast.parse(chunk_candidate)
            except Exception:
                continue
            payloads.append((chunk_label, chunk_candidate, "fallback_chunk"))

    return payloads


def main():
    parser = argparse.ArgumentParser(description="Prepare fuzz_pycompile corpus from Lib/test .py files")
    parser.add_argument("--lib-test-root", required=True, help="Path to cpython-src/Lib/test")
    parser.add_argument("--out-dir", required=True, help="Output directory for prepared corpus")
    parser.add_argument("--max-payload", type=int, default=16380, help="Max payload bytes without 3-byte prefix")
    args = parser.parse_args()

    lib_test_root = pathlib.Path(args.lib_test_root).resolve()
    out_dir = pathlib.Path(args.out_dir).resolve()
    seed_dir = out_dir / "seeds"
    meta_dir = out_dir / "meta"
    seed_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    py_files = sorted(lib_test_root.rglob("*.py"))
    records = []
    skipped = []

    counters = {
        "total_py_files": len(py_files),
        "small_files": 0,
        "large_files": 0,
        "parsed_ok": 0,
        "parsed_fail": 0,
        "files_with_seed": 0,
        "files_without_seed": 0,
        "seeds_written": 0,
    }

    for path in py_files:
        raw_bytes = path.read_bytes()
        rel_path = path.relative_to(lib_test_root)
        file_has_seed = False

        if len(raw_bytes) <= args.max_payload:
            counters["small_files"] += 1
            base_id = snippet_id(rel_path, "full_file", raw_bytes.decode("utf-8", "ignore"))
            write_seed_variants(
                seed_dir,
                base_id,
                raw_bytes,
                records,
                rel_path,
                "full_file",
            )
            counters["seeds_written"] += len(PREFIXES)
            file_has_seed = True
        else:
            counters["large_files"] += 1
            text = read_source_text(path)
            if text is None:
                counters["parsed_fail"] += 1
                skipped.append({"source_file": str(rel_path), "reason": "tokenize_read_failed"})
            else:
                try:
                    payloads = build_large_file_payloads(path, text, args.max_payload)
                    counters["parsed_ok"] += 1
                except Exception:
                    payloads = []
                    counters["parsed_fail"] += 1
                    skipped.append({"source_file": str(rel_path), "reason": "ast_parse_failed"})

                if payloads:
                    for label, payload_text, strategy in payloads:
                        payload_bytes = to_payload_bytes(payload_text)
                        base_id = snippet_id(rel_path, label, payload_text)
                        write_seed_variants(
                            seed_dir,
                            base_id,
                            payload_bytes,
                            records,
                            rel_path,
                            strategy,
                        )
                        counters["seeds_written"] += len(PREFIXES)
                    file_has_seed = True
                else:
                    skipped.append({"source_file": str(rel_path), "reason": "no_valid_slice_under_limit"})

        if file_has_seed:
            counters["files_with_seed"] += 1
        else:
            counters["files_without_seed"] += 1

    csv_path = meta_dir / "seed_manifest.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["seed_file", "source_file", "strategy", "payload_bytes", "seed_bytes"],
        )
        writer.writeheader()
        writer.writerows(records)

    skipped_path = meta_dir / "skipped_files.json"
    skipped_path.write_text(json.dumps(skipped, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        **counters,
        "seed_dir": str(seed_dir),
        "seed_count": len(records),
        "manifest_csv": str(csv_path),
        "skipped_json": str(skipped_path),
        "max_payload": args.max_payload,
        "prefixes_hex": [prefix.hex() for prefix in PREFIXES],
    }

    summary_path = meta_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
