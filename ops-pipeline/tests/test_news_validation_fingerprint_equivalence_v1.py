"""Exact digest compatibility with the original full-byte inventory reader."""
import hashlib
import os
from pathlib import Path
import stat
from types import SimpleNamespace
import pytest
from profile_compatibility_release_v1_2 import validation_fingerprint
import profile_compatibility_release_v1_2 as owner

def original_fingerprint(roots):
    from human_review_operations_v1 import io_path
    digest=hashlib.sha256()
    def include(value):
        if isinstance(value,str):value=value.encode('utf-8')
        digest.update(len(value).to_bytes(8,'big'));digest.update(value)
    try:
        for root in roots:
            include(str(root))
            for name in ('data','output'):
                directory=io_path(root/name);include(str(directory))
                if not directory.is_dir():include(name+':missing');continue
                for path in sorted(directory.rglob('*')):
                    relative=path.relative_to(directory)
                    if '.locks' in relative.parts:continue
                    if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):return None
                    include(name+'/'+relative.as_posix());include('file' if path.is_file() else 'directory')
                    if path.is_file():include(hashlib.sha256(path.read_bytes()).digest())
        for name in ('novel_news_v1.py','news_delivery_v1.py'):
            include(Path(owner.__file__).with_name(name).read_bytes())
    except OSError:return None
    return digest.hexdigest()

@pytest.mark.parametrize('mutation',['none','same_size_same_mtime','add_file','remove_file','empty_directory','rename','output_bytes','locks_only','missing_output','multiple_roots'])
def test_exact_original_digest_and_invalidation(tmp_path,mutation):
    root=tmp_path/'runtime';(root/'data/a/nested').mkdir(parents=True);(root/'output').mkdir()
    for name,raw in [('a.json',b'{"value":1}\n'),('a-/name.json',b'2'),('A_2/中文.json',b'3'),
                     ('a/nested/s.json',b'4'),('a.Z.json',b'5')]:
        path=root/'data'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    target=root/'data/a.json';roots=(root,)
    initial=validation_fingerprint(roots)
    assert initial==original_fingerprint(roots) and initial is not None
    if mutation=='same_size_same_mtime':
        stamp=target.stat();target.write_bytes(b'{"value":2}\n');os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    elif mutation=='add_file':(root/'data/extra.json').write_bytes(b'{}')
    elif mutation=='remove_file':target.unlink()  # disposable pytest fixture only
    elif mutation=='empty_directory':(root/'data/empty').mkdir()
    elif mutation=='rename':target.rename(root/'data/renamed.json')
    elif mutation=='output_bytes':(root/'output/published.xlsx').write_bytes(b'PK-exact-source')
    elif mutation=='locks_only':
        path=root/'data/a/.locks/nested/untrusted.lock';path.parent.mkdir(parents=True);path.write_bytes(b'operational only')
    elif mutation=='missing_output':(root/'output').rmdir()  # verified empty disposable directory
    elif mutation=='multiple_roots':
        other=tmp_path/'qualification';(other/'data').mkdir(parents=True);(other/'data/proof.json').write_bytes(b'{}');roots=(root,other)
    result=validation_fingerprint(roots)
    assert result==original_fingerprint(roots) and result is not None
    assert (result==initial)==(mutation in {'none','locks_only'})

@pytest.mark.parametrize('kind',['symlink','junction','unreadable'])
def test_fresh_metadata_and_read_failures_disable_reuse(tmp_path,monkeypatch,kind):
    root=tmp_path/'runtime';(root/'data').mkdir(parents=True)
    target=root/'data/evidence.json';target.write_bytes(b'{}')
    original=os.lstat
    def lstat(path,*args,**kwargs):
        if Path(path).name=='evidence.json':
            if kind=='unreadable':raise PermissionError('isolated evidence unavailable')
            return SimpleNamespace(st_mode=stat.S_IFLNK if kind=='symlink' else stat.S_IFREG,
                st_reparse_tag=getattr(stat,'IO_REPARSE_TAG_MOUNT_POINT',-1) if kind=='junction' else 0)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(os,'lstat',lstat)
    assert validation_fingerprint((root,)) is None
