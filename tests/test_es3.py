"""Parse the actual host sources as ES3; modern Node syntax checks miss byte."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from illona_mcp.bridge import HOST, IllonaBridge


PARSE_ES3 = r"""
const fs = require('fs');
const vm = require('vm');
const source = process.binding('natives')['internal/deps/acorn/acorn/dist/acorn'];
if (!source) {
    process.stderr.write('This Node build does not expose its bundled Acorn parser.');
    process.exit(77);
}
const context = {exports: {}};
context.module = {exports: context.exports};
vm.runInNewContext(source, context);
const acorn = context.module.exports;
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = cases.map(function (item) {
    try {
        acorn.parse(item.source, {ecmaVersion: 3, allowReserved: false});
        return {name: item.name, parsed: true};
    } catch (error) {
        return {name: item.name, parsed: false, message: error.message};
    }
});
process.stdout.write(JSON.stringify(results));
"""


def parse_es3(cases: list[dict]) -> list[dict]:
    candidate = os.getenv("ILLONA_TEST_NODE") or shutil.which("node")
    if not candidate:
        candidate = str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
    if not Path(candidate).is_file():
        pytest.skip("Node is unavailable for strict ES3 host parsing")
    completed = subprocess.run(
        [candidate, "-e", PARSE_ES3],
        input=json.dumps(cases), text=True, capture_output=True, timeout=20,
    )
    if completed.returncode == 77:
        pytest.skip(completed.stderr)
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def test_all_shipped_jsx_modules_parse_as_strict_es3():
    modules = sorted(HOST.glob("*.jsx"))
    assert {module.name for module in modules} >= {"core.jsx", "drawing.jsx", "layout.jsx", "production.jsx"}
    results = parse_es3([{"name": module.name, "source": module.read_text(encoding="utf-8")} for module in modules])
    assert all(result["parsed"] for result in results), results


def test_full_generated_bridge_bundle_parses_as_strict_es3(tmp_path):
    bridge = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")
    bundle = bridge._bundle(
        "create_elements",
        {"document_id": "doc-example", "elements": [{"type": "text", "text": "România 😊 \"\\\n\u2028\u2029"}]},
        tmp_path / "receipt with spaces și diacritice" / "result.json",
    )
    # #target/#targetengine belong to ExtendScript's preprocessor, not ES3.
    source = "\n".join(line for line in bundle.splitlines() if not line.lstrip().startswith("#target"))
    result = parse_es3([{"name": "full-generated-bridge", "source": source}])[0]
    assert result["parsed"], result


def test_parser_rejects_future_reserved_byte_and_modern_syntax():
    results = parse_es3([
        {"name": "reserved-byte-regression", "source": "function byte(at) { return at & 255; }"},
        {"name": "modern-syntax-negative-control", "source": "const value = (x) => x + 1;"},
        {"name": "es3-positive-control", "source": "function readByte(at) { return at & 255; }"},
    ])
    assert results[0]["parsed"] is False and "reserved" in results[0]["message"].lower(), results
    assert results[1]["parsed"] is False, results
    assert results[2]["parsed"] is True, results
