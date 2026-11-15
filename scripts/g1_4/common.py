"""Utilities for private research artifacts, not runtime user-input storage."""
from pathlib import Path
import sys
import json
import tempfile
import shutil
from contextlib import contextmanager
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'services/training'))
sys.path.insert(0,str(ROOT/'scripts/g1'))
import train_url_baselines as base
import prepare_urls as prep


def rows(path):
    with path.open(encoding='utf-8') as f:
        for line in f:yield json.loads(line)


def write_rows(path, values):
    with path.open('w',encoding='utf-8',newline='\n') as f:
        for row in values:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n')


@contextmanager
def output_dir(target):
    if target.exists():raise base.TrainingError('Output exists; choose a new directory.')
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.g14-staging-',dir=target.parent))
    try:
        yield stage
        if target.exists():raise base.TrainingError('Output appeared during preparation.')
        stage.rename(target)
    finally:
        if stage.exists():shutil.rmtree(stage)


def checked_file(folder,manifest,name):
    if base.sha(folder/name)!=manifest['files'][name]:raise base.TrainingError('Input checksum mismatch: '+name)


def save_manifest(folder, metadata):
    base.write_json(folder/'manifest.json',{**metadata,'files':{p.name:base.sha(p) for p in sorted(folder.iterdir())}})


def run(main):
    try:main()
    except (OSError,ValueError,KeyError,TypeError) as e:
        message=str(e) if isinstance(e,base.TrainingError) else type(e).__name__+': check files/environment; no input contents printed.'
        print('ERROR: '+message,file=sys.stderr);raise SystemExit(1)
