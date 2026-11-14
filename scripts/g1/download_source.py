"""Download only the locked UCI archive, never URLs contained in the dataset."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile

LIMIT = 128 * 1024 * 1024

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def bounded_copy(source, destination):
    size = 0
    with destination.open('wb') as stream:
        while block := source.read(1024 * 1024):
            size += len(block)
            if size > LIMIT:
                raise ValueError('Source exceeds download/extraction size limit.')
            stream.write(block)


def download(output_dir):
    lock = json.loads(Path(__file__).with_name('source-lock.json').read_text(encoding='utf-8'))
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / 'phiusiil.csv'
    if target.exists():
        if sha(target) == lock['csv_sha256']:
            return {'status': 'already_verified', 'csv_sha256': lock['csv_sha256']}
        raise ValueError('Existing phiusiil.csv differs from lock; use a new source directory.')
    with tempfile.TemporaryDirectory(prefix='.uci-download-', dir=output_dir) as folder:
        temp = Path(folder)
        archive = temp / 'source.zip'
        request = urllib.request.Request(lock['source_url'], headers={'User-Agent': 'phishing-detector-research/1.0'})
        with urllib.request.urlopen(request, timeout=90) as response:
            bounded_copy(response, archive)
        if sha(archive) != lock['archive_sha256']:
            raise ValueError('Archive checksum mismatch. Do not change the lock to bypass this failure.')
        csv_path = temp / 'phiusiil.csv'
        with zipfile.ZipFile(archive) as z:
            csvs = [item for item in z.infolist() if not item.is_dir() and item.filename.lower().endswith('.csv')]
            if len(csvs) != 1 or csvs[0].file_size > LIMIT:
                raise ValueError('Unexpected archive contents.')
            # Read a member into a fixed filename; never extract arbitrary archive paths.
            with z.open(csvs[0]) as source:
                bounded_copy(source, csv_path)
        if sha(csv_path) != lock['csv_sha256']:
            raise ValueError('CSV checksum mismatch.')
        # Exclusive creation: never replace an existing source file.
        try:
            with target.open('xb') as destination, csv_path.open('rb') as source:
                shutil.copyfileobj(source, destination)
        except FileExistsError:
            raise ValueError('Output appeared during download; check the existing source.') from None
    return {'status': 'downloaded_and_verified', 'csv_sha256': lock['csv_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(download(args.output_dir), indent=2))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print('ERROR: ' + (str(error) if type(error) is ValueError else type(error).__name__ + ': download failed.'), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
