"""Replay verifier-v2 from a clean exact runtime and seal its aggregate Grok receipt."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from study import binding, canonical


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def write(output: Path, receipt: dict) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite Grok verifier replay output")
    output.mkdir(parents=True)
    path = output / "receipt.json"; path.write_bytes(canonical(receipt) + b"\n")
    (output / "manifest.json").write_bytes(canonical({"format_version": 1, "kind": "grok_verifier_v2_replay", "files": {"receipt.json": binding(path)}}) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grok-work-root", required=True, type=Path)
    parser.add_argument("--verifier-manifest-dir", required=True, type=Path)
    parser.add_argument("--clean-verifier-runtime-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    verifier_output = args.verifier_manifest_dir.resolve()
    existing = read(verifier_output / "verification-manifest.json")
    expected_runtime = existing.get("verifier_runtime", {}).get("analyzer", {})
    expected_corpus = existing.get("corpus", {})
    root = args.clean_verifier_runtime_root.resolve()
    source = root / "evaluation-results" / "hbq-human-alignment-supplemental-providers-verifier-v2" / "analyze_study.py"
    if not source.is_file() or binding(source) != {"bytes": expected_runtime.get("bytes"), "sha256": expected_runtime.get("sha256")}:
        raise ValueError("Clean verifier-v2 runtime is not the exact sealed revision")
    script = """import hashlib,importlib.util,json,sys\nfrom pathlib import Path\nroot,work,out=[Path(x) for x in sys.argv[1:]]\nsys.path.insert(0,str(root/'src'))\npath=root/'evaluation-results'/'hbq-human-alignment-supplemental-providers-verifier-v2'/'analyze_study.py'\nspec=importlib.util.spec_from_file_location('grok_replay',path); m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)\nv=m.verify_verification_manifest(work,'grok_4_6_high','development',out)\nc=v['corpus']; raw=work/'runs'/'grok_4_6_high'/'development'\ndef b(p): return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}\nitem_ids=sorted(p.name for p in raw.iterdir() if p.is_dir())\nprojection=[{'item_id':i,'run':b(raw/i/'run-01'/'run.json'),'score':b(raw/i/'run-01'/'score.json'),'verdicts':b(raw/i/'run-01'/'verdicts.jsonl')} for i in item_ids]\ndigest=hashlib.sha256(json.dumps(projection,sort_keys=True,separators=(',',':')).encode()).hexdigest()\nprint(json.dumps({'provider_id':c['provider_id'],'phase':c['phase'],'run_count':c['run_count'],'checkpoint_count':c['checkpoint_count'],'root_sha256':c['root_commitment']['sha256'],'accepted_projection':{'item_count':len(projection),'item_ids':item_ids,'sha256':digest}},separators=(',',':')))\n"""
    env = dict(os.environ); env["PYTHONIOENCODING"] = "utf-8"; env["PYTHONUTF8"] = "1"
    completed = subprocess.run([sys.executable, "-c", script, str(root), str(args.grok_work_root.resolve()), str(verifier_output)], text=True, encoding="utf-8", capture_output=True, timeout=3600, check=False, env=env)
    if completed.returncode != 0:
        raise ValueError(f"Grok verifier-v2 replay failed: {completed.stderr.strip() or completed.stdout.strip()}")
    result = json.loads(completed.stdout)
    required = {"provider_id": "grok_4_6_high", "phase": "development", "run_count": 88, "checkpoint_count": 528, "root_sha256": expected_corpus.get("root_commitment", {}).get("sha256")}
    if {key: result.get(key) for key in required} != required or not isinstance(result.get("accepted_projection"), dict) or result["accepted_projection"].get("item_count") != 88:
        raise ValueError("Grok verifier-v2 replay does not bind the sealed corpus")
    write(args.output_dir.resolve(), {"format_version": 1, "kind": "grok_verifier_v2_replay", "result": result, "inputs": {"existing_verification_manifest": binding(verifier_output / "verification-manifest.json"), "clean_verifier_runtime": binding(source), "raw_frozen_contract": binding(args.grok_work_root.resolve() / "frozen-provider-contract.json")}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
