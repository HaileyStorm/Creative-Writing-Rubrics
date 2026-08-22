"""Replay the pinned Fresh88 historical verifier and seal only its aggregate receipt."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from study import binding, canonical


def write(output: Path, receipt: dict) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite Fresh88 verifier replay output")
    output.mkdir(parents=True)
    path = output / "receipt.json"; path.write_bytes(canonical(receipt) + b"\n")
    (output / "manifest.json").write_bytes(canonical({"format_version": 1, "kind": "fresh88_historical_verifier_replay", "files": {"receipt.json": binding(path)}}) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--authority-dir", required=True, type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--historical-runtime-root", required=True, type=Path)
    parser.add_argument("--analysis-runtime-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.analysis_runtime_root.resolve()
    source = root / "evaluation-results" / "hbq-human-alignment-v3-fresh88-analysis-v1" / "analyze.py"
    if not source.is_file():
        raise ValueError("Fresh88 analysis runtime is missing")
    script = """import hashlib,importlib.util,json,sys\nfrom pathlib import Path\nroot,data,work,authority,artifacts,runtime=[Path(x) for x in sys.argv[1:]]\npath=root/'evaluation-results'/'hbq-human-alignment-v3-fresh88-analysis-v1'/'analyze.py'\nsys.path.insert(0,str(path.parent))\nspec=importlib.util.spec_from_file_location('fresh88_replay',path); m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)\nfrozen,receipt,plan,work_artifacts=m._load_inputs(work,authority,artifacts,runtime)\nverified=m._historical_verify(runtime,plan,artifacts)\nmatrix=m._verify_matrix_gate(plan,work_artifacts,verified)\ndef b(p): return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}\nitem_ids=sorted(p.name for p in (artifacts/'runs').iterdir() if p.is_dir())\nprojection=[{'item_id':i,'run':b(artifacts/'runs'/i/'run.json'),'score':b(artifacts/'runs'/i/'score.v2.json'),'verdicts':b(artifacts/'runs'/i/'verdicts.jsonl')} for i in item_ids]\ndigest=hashlib.sha256(json.dumps(projection,sort_keys=True,separators=(',',':')).encode()).hexdigest()\nprint(json.dumps({'matrix_sha256':matrix['matrix_sha256'],'record_count':len(verified),'analysis_runtime':{'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},'accepted_projection':{'item_count':len(projection),'item_ids':item_ids,'sha256':digest}},separators=(',',':')))\n"""
    env = dict(os.environ); env["PYTHONIOENCODING"] = "utf-8"; env["PYTHONUTF8"] = "1"
    completed = subprocess.run([sys.executable, "-c", script, str(root), str(args.data_dir.resolve()), str(args.work_dir.resolve()), str(args.authority_dir.resolve()), str(args.artifact_dir.resolve()), str(args.historical_runtime_root.resolve())], text=True, encoding="utf-8", capture_output=True, timeout=3600, check=False, env=env)
    if completed.returncode != 0:
        raise ValueError(f"Fresh88 historical verifier replay failed: {completed.stderr.strip() or completed.stdout.strip()}")
    result = json.loads(completed.stdout)
    if result.get("record_count") != 88 or not isinstance(result.get("matrix_sha256"), str):
        raise ValueError("Fresh88 historical verifier replay produced an invalid receipt")
    receipt = {"format_version": 1, "kind": "fresh88_historical_verifier_replay", "result": result, "inputs": {"data": binding(args.data_dir.resolve() / "hanna_stories_annotations.csv"), "work_contract": binding(args.work_dir.resolve() / "fresh88-execution-contract.json"), "authority_contract": binding(args.authority_dir.resolve() / "frozen-successor-contract.json"), "artifact_root_marker": binding(args.artifact_dir.resolve() / "runs" / "hanna-10" / "run.json"), "historical_runtime": binding(args.historical_runtime_root.resolve() / "evaluation-results" / "hbq-human-alignment-v3" / "analyze_study.py")}}
    write(args.output_dir.resolve(), receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
