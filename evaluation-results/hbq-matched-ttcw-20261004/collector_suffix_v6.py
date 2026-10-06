"""TTCW010 native-once continuation after the saved own TTCW009 return."""
import ast
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SOURCE_COLLECTOR_SHA = 'c4d9cc6a6ec3744d1af9c844a2e4841eda648bcf856e1a8bd0c29c7f5840bc2f'
path = HERE / 'collector_suffix_v5.py'
import hashlib
raw = path.read_bytes()
if hashlib.sha256(raw).hexdigest() != SOURCE_COLLECTOR_SHA:
    raise ValueError('Pinned009 collector differs')
spec = importlib.util.spec_from_file_location('ttcw010_private009', path)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
base = dict(vars(source))
PROGRAM, REPO, native, require, sha, canonical = (base[k] for k in ('PROGRAM', 'REPO', 'native', 'require', 'sha', 'canonical'))
POLICY = 'ttcw_untouched_suffix_execution_v6'
MANIFEST_SHA = '40e6eca06ea4229fc45c4c35ff535b211139e3711d35d2c1b71c33ba0f6be6e1'
CONTENT_SHA = '3194cea1fd452ebc15dbe7e6a36c85b3fae2e372e3d2855c942d5abfe047ee06'
SOURCE_SHA = 'b3ae25cbd36674bdffdedf4c4cf58a2e51be109b86f183b72b3b490d70dd0137'
SOURCE_JOB_SHA = '205fa196f3dae148d83a62043530f29211940099d547e8b8baddac7a70b6eab5'
INVENTORY_SHA = 'f6b4efeed051656951d387a01c20b1668a7f9b5c530971ea587081def2989589'
RELEASE_SHA = '44742e87f71a8b07e3762c627fb23f2e773447eb93c41aa90140799c5b06510d'
LIFECYCLE = PROGRAM / 'ttcw-phase1/grok-suffix-010-lifecycle/full-001'
SOURCE_MANIFEST_PATH = PROGRAM / 'ttcw-phase1/frozen-grok-suffix-009/manifest.json'
SOURCE_RETURN_PATH = PROGRAM / 'ttcw-phase1/ttcw-suffix009-return-001/receipt.json'
native.MANIFEST_SHA, native.POLICY = MANIFEST_SHA, POLICY


class Contract(ast.NodeTransformer):
    def visit_Constant(self, node):
        values = {337: 421, 338: 422, 1217: 1133, 322: 337, 323: 338}
        if type(node.value) is int and node.value in values:
            node.value = values[node.value]
        elif isinstance(node.value, str):
            if node.value == 'retained_release_invocation_sha256':
                node.value = 'retained_source_return_receipt_sha256'
            elif len(node.value) != 64:
                node.value = node.value.replace('009', '010').replace('Reserved337/untouched338', 'Reserved421/untouched422')
        return node


tree = ast.parse(raw)
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('guard', 'load_manifest', 'job_binding', 'collect_one', 'replay', 'main')]
for function in functions:
    if function.name == 'load_manifest':
        text = ast.get_source_segment(raw.decode(), function)
        text = text.replace("latest['collector_sha256'] == V4_SHA", "latest['collector_sha256'] == SOURCE_COLLECTOR_SHA")
        begin, end = text.index('    inherited = jobs[-2]'), text.index('    for retained,receipt in zip(')
        text = text[:begin] + '''    source_path = SOURCE_MANIFEST_PATH
    previous_raw = source_path.read_bytes()
    require(sha(previous_raw) == SOURCE_SHA, 'Exact previous frozen source differs')
    previous = json.loads(previous_raw)['continuation']
    require(jobs[:-1] == previous['prefix_jobs'] and receipts[:337] == previous['prefix_receipts'],
        'Inherited prefix metadata must remain byte-equivalent in meaning')
    return_raw = SOURCE_RETURN_PATH.read_bytes()
    require(sha(return_raw) == RELEASE_SHA, 'Saved own return receipt differs')
    saved = json.loads(return_raw)
    require(saved['source_terminal_metadata_inventory'] == inventory and saved['source_job_sha256'] == SOURCE_JOB_SHA
        and saved['source_manifest_sha256'] == SOURCE_SHA and saved['released_local_workers'] == 2
        and saved['source_answers_opened'] is False and saved['source_admissions_replayed'] is False,
        'Latest prefix must be the saved own metadata inventory, without another audit')
''' + text[end:]
        replacement = ast.parse(text).body[0]
        # The new source-prefix comparison already uses the literal337 inherited cutoff.
        replacement = Contract().visit(replacement)
        for n in ast.walk(replacement):
            if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == 'receipts'
                    and isinstance(n.slice, ast.Slice) and n.slice.lower is None):
                n.slice.upper = ast.Constant(337)
        functions[functions.index(function)] = replacement
    else:
        Contract().visit(function)
base.update(__file__=str(Path(__file__).resolve()), **{k: v for k, v in globals().items() if k.isupper()})
exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])), 'pinned_ttcw010_execution', 'exec'), base)
native.guard = base['guard']
guard, load_manifest, job_binding, collect_one, replay, main = (base[k] for k in ('guard', 'load_manifest', 'job_binding', 'collect_one', 'replay', 'main'))
v4, Event, TOOLS, ROUTE_SHA = (base[k] for k in ('v4', 'Event', 'TOOLS', 'ROUTE_SHA'))


if __name__ == '__main__':
    raise SystemExit(main())
