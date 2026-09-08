"""One-at-a-time disposable OCR worker. No torch in the web process."""
import os
import hashlib
import json
import threading
from gp_core import normalize_item_code
OCR_BUILD = "GP-OCR-CPU-LITE-v4"
OCR_TIMEOUT_SECONDS = 240
OCR_MAX_WORKER_MB = 850
OCR_MAX_UPLOAD_BYTES = 12 * 1024 * 1024
_SCAN_LOCK = threading.Lock()

def free_ocr_status():
    """Check installation without loading any neural-network libraries."""
    import importlib.util
    from pathlib import Path
    worker = Path(__file__).resolve().with_name('invoice_ocr_worker.py')
    if not worker.is_file():
        return (False, '', 'Missing invoice_ocr_worker.py; upload all three bundle files.')
    missing = [name for name in ('easyocr', 'torch', 'torchvision') if importlib.util.find_spec(name) is None]
    if missing:
        return (False, '', 'Missing packages: ' + ', '.join(missing))
    return (True, 'en/numbers', OCR_BUILD + ' | free local code/quantity reader')

def _ocr_scan_lock():
    return _SCAN_LOCK

def _ocr_memory_state():
    """Best-effort Linux cgroup memory figures, in bytes (v2 or v1)."""
    from pathlib import Path
    candidates = [('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory.current'), ('/sys/fs/cgroup/memory/memory.limit_in_bytes', '/sys/fs/cgroup/memory/memory.usage_in_bytes')]
    for limit_path, current_path in candidates:
        try:
            limit = int(Path(limit_path).read_text().strip())
            current = int(Path(current_path).read_text().strip())
            if 0 < limit < 2 ** 60 and current >= 0:
                return (limit, current)
        except (OSError, ValueError):
            continue
    return (None, None)

def _ocr_worker_rss(pid):
    from pathlib import Path
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0

def _ocr_stop_worker(process):
    import subprocess
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

def _run_ocr_worker(image_bytes, worker_path=None, timeout=None, max_worker_mb=None):
    """Run one disposable worker; release model RAM when the scan finishes.

    Timeout and memory guards are best-effort. A host-level OOM kill can still
    happen faster than the guard, so this does not guarantee host availability.
    """
    from pathlib import Path
    import subprocess
    import sys
    import tempfile
    import time
    if not image_bytes or len(image_bytes) > OCR_MAX_UPLOAD_BYTES:
        raise ValueError('Use an invoice image smaller than 12 MB.')
    worker = Path(worker_path) if worker_path else Path(__file__).resolve().with_name('invoice_ocr_worker.py')
    if not worker.is_file():
        raise RuntimeError('Missing invoice_ocr_worker.py. Upload it next to inventory_tracker.py.')
    seconds = OCR_TIMEOUT_SECONDS if timeout is None else float(timeout)
    worker_limit = OCR_MAX_WORKER_MB if max_worker_mb is None else float(max_worker_mb)
    mib = 1024 * 1024
    limit, current = _ocr_memory_state()
    if limit is not None and limit - current < 350 * mib:
        raise RuntimeError('Not enough free host memory to start OCR safely. Use manual entry and reboot the app.')
    print(f'[{OCR_BUILD}] scan_start memory_limit_mb={(None if limit is None else limit // mib)} memory_used_mb={(None if current is None else current // mib)}', flush=True)
    with tempfile.TemporaryDirectory(prefix='gp_ocr_') as temp:
        folder = Path(temp)
        image_path, output_path = (folder / 'input_image', folder / 'result.json')
        log_path = folder / 'worker.log'
        image_path.write_bytes(image_bytes)
        env = os.environ.copy()
        for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            env[name] = '1'
        env.update({'CUDA_VISIBLE_DEVICES': '', 'PYTHONUNBUFFERED': '1', 'MALLOC_ARENA_MAX': '2'})
        process = None
        stopped_reason = ''
        try:
            with log_path.open('w', encoding='utf-8') as logfile:
                process = subprocess.Popen([sys.executable, '-u', str(worker), str(image_path), str(output_path)], stdout=logfile, stderr=subprocess.STDOUT, env=env, cwd=str(worker.parent))
                start = time.monotonic()
                peak_rss = 0
                while process.poll() is None:
                    rss = _ocr_worker_rss(process.pid)
                    peak_rss = max(peak_rss, rss)
                    limit, current = _ocr_memory_state()
                    if time.monotonic() - start > seconds:
                        stopped_reason = 'OCR timed out. The first model download may need another attempt.'
                    elif rss > worker_limit * mib:
                        stopped_reason = 'OCR reached its memory safety limit. No stock was changed; use manual entry.'
                    elif limit is not None and current > limit - max(64 * mib, int(limit * 0.08)):
                        stopped_reason = 'OCR stopped because the host is close to its memory limit. No stock was changed.'
                    if stopped_reason:
                        _ocr_stop_worker(process)
                        break
                    time.sleep(0.15)
                print(f'[{OCR_BUILD}] worker_returncode={process.returncode} worker_peak_rss_mb={peak_rss // mib}', flush=True)
        finally:
            if process is not None:
                _ocr_stop_worker(process)
            if log_path.exists():
                print(log_path.read_text(encoding='utf-8', errors='replace')[-20000:], flush=True)
        if stopped_reason:
            raise RuntimeError(stopped_reason)
        if process is None:
            raise RuntimeError('The OCR worker could not be started.')
        if not output_path.is_file():
            raise RuntimeError(f'OCR worker stopped without a result (exit {process.returncode}). Stock was not changed. Download the log containing GP-OCR-CPU-LITE-v4.')
        if output_path.stat().st_size > 512 * 1024:
            raise RuntimeError('Invalid oversized OCR response.')
        try:
            result = json.loads(output_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as error:
            raise RuntimeError('The OCR worker returned invalid data.') from error
        if not isinstance(result, dict) or not result.get('ok'):
            detail = result.get('error', 'Unknown OCR error') if isinstance(result, dict) else 'Invalid OCR response'
            raise RuntimeError(str(detail))
        if process.returncode != 0:
            raise RuntimeError(f'OCR worker failed with exit {process.returncode}.')
        data = result.get('data')
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise RuntimeError('OCR response has no valid item list.')
        return data

def extract_invoice_data(uploaded_file, stock_df=None):
    """Read through the isolated worker; match names in the parent only."""
    import math
    image_bytes = uploaded_file.getvalue()
    lock = _ocr_scan_lock()
    if not lock.acquire(blocking=False):
        raise RuntimeError('Another invoice scan is running. Try again after it finishes.')
    try:
        result = _run_ocr_worker(image_bytes)
    finally:
        lock.release()
    if len(result['items']) > 60:
        raise RuntimeError('Too many OCR rows; use manual entry.')
    result.setdefault('warnings', [])
    code_names = {}
    if stock_df is not None:
        for _, row in stock_df.iterrows():
            code = normalize_item_code(row.get('رمز المادة', ''))
            name = str(row.get('اسم المادة', '') or '')
            if code:
                code_names.setdefault(code, set()).add(name)
    for item in result['items']:
        if not isinstance(item, dict):
            raise RuntimeError('Invalid OCR row.')
        code = str(item.get('item_code', '')).strip()
        item['item_code'] = code
        names = code_names.get(code, set())
        item['item_name'] = next(iter(names)) if len(names) == 1 else ''
        if not item['item_name']:
            result['warnings'].append(f'Code {code}: no unique exact stock name; review manually.')
        quantity = item.get('quantity')
        if quantity is not None:
            try:
                value = float(quantity)
            except (ValueError, TypeError) as error:
                raise RuntimeError('Invalid OCR quantity.') from error
            if not math.isfinite(value) or value <= 0:
                raise RuntimeError('Invalid OCR quantity.')
            item['quantity'] = value
    result['image_hash'] = hashlib.sha256(image_bytes).hexdigest()
    result['source_name'] = getattr(uploaded_file, 'name', 'invoice-photo.jpg')
    return result
