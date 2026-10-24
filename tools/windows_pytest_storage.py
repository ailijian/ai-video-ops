"""Explicit pytest storage adapter for Windows; no test selection or gate changes."""
from pathlib import Path
import json
import secrets


def allocate(parent):
    parent = Path(parent).resolve()
    if parent.name != '.verify' or not parent.is_dir():
        raise ValueError('Explicit project .verify storage is required')
    for _ in range(512):
        target = parent / secrets.token_hex(4)
        try:
            target.mkdir()
        except FileExistsError:
            continue
        if target.resolve().parent != parent:
            raise ValueError('Verification storage escaped its project')
        return target
    raise RuntimeError('No unused short verification root; retain evidence and choose a new run')


def pytest_addoption(parser):
    parser.addoption('--aivo-short-temp-root', required=True)


def pytest_configure(config):
    target = allocate(config.getoption('--aivo-short-temp-root'))
    # pytest may remove/recreate its basetemp. Keep an atomic claimed parent
    # outside that cleanup boundary so concurrent workers cannot claim it.
    config.option.basetemp = str(target / 't')
    config._aivo_short_storage = target
    (target / 'VERIFICATION_STORAGE.json').write_text(json.dumps({
        'purpose':'isolated verification storage only','source_or_authority_patched':False,
        'pytest_args':list(config.invocation_params.args)},indent=2),encoding='utf-8')


def pytest_report_header(config):
    return 'Project-isolated short Windows temp root: ' + str(config._aivo_short_storage)
