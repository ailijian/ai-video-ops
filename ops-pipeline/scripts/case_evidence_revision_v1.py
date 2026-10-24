"""Append-only Human evidence revisions and the single effective Case target.

The caller must hold the Case operation lock. Console callers additionally hold
the current reviewer lock. Records are companions of the ORIGINAL Attempt; a
build execution never becomes a submission or a new Attempt. No model runs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import re

from human_review_operations_v1 import digest, file_sha, read, write_once, io_path

EDIT_VERSION = "case-human-evidence-edit-v1.0"
REVISION_VERSION = "case-human-evidence-revision-v1.0"
VALIDATION_VERSION = "case-human-evidence-revision-validation-v1.0"
POLICY_VERSION = "case-evidence-confirmation-policy-v1.0"
FINAL_VERSION = "case-evidence-final-review-v2.0"
KNOWN_BOUNDARY_REASONS = {'video_start','same_shot_motion','text_overlay_change_only',
    'scene_or_location_change','camera_view_change','subject_or_action_discontinuity','uncertain'}
ID = re.compile(r"[A-Za-z0-9_-]{1,160}\Z")
OPERATION = re.compile(r"[a-f0-9]{32}\Z")


class RevisionError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fail(code, message):
    raise RevisionError(code, message)


def within(root, value):
    root = Path(root).resolve()
    raw = str(value)
    if raw.startswith('\\\\?\\'):
        raw = raw[4:]
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        fail("CASE_REVISION_SOURCE_INVALID", "修订来源不在当前合法对象内。")
    return resolved


def ref(root, path):
    path = within(root, path)
    if not io_path(path).is_file():
        fail("CASE_REVISION_SOURCE_UNAVAILABLE", "原始证据暂不可用，不能凭空修订。")
    return {"path": path.relative_to(Path(root).resolve()).as_posix(), "sha256": file_sha(path)}


def check_ref(root, reference):
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        fail("CASE_REVISION_SOURCE_INVALID", "修订来源引用不完整。")
    path = within(root, reference["path"])
    if ref(root, path) != reference:
        fail("CASE_REVISION_SOURCE_STALE", "修订来源已变化，请重新核对。")
    return path


def attempt_root(pipeline_root, case_id, attempt_id):
    if not all(isinstance(x, str) and ID.fullmatch(x) for x in (case_id, attempt_id)):
        fail("CASE_REVISION_ID_INVALID", "案例或投稿身份无效。")
    return within(pipeline_root, Path("data/case_analysis_attempts") / case_id / attempt_id)


def original_target(pipeline_root, case_id, attempt_id):
    directory = attempt_root(pipeline_root, case_id, attempt_id)
    state = read(directory / "case_analysis_attempt_v1.json")
    path = within(directory, state.get("artifacts", {}).get("case_candidate_v1", ""))
    if (state.get("case_id") != case_id or state.get("attempt_id") != attempt_id
            or not path.is_file() or read(path).get("case_id") != case_id):
        fail("CASE_REVISION_SOURCE_INVALID", "原投稿与候选身份不一致。")
    return directory, path, state


def root_for_candidate(candidate_path):
    """Resolve from exact lineage, never a fixed number of directory parents."""
    path = Path(candidate_path).resolve()
    case = read(path)
    attempt_id = case.get("analysis_lineage", {}).get("attempt_id")
    for directory in path.parents:
        state_path = directory / "case_analysis_attempt_v1.json"
        if state_path.is_file():
            state = read(state_path)
            legacy_exact = (attempt_id is None and within(directory,state.get('artifacts',{}).get('case_candidate_v1',''))==path)
            if (state.get("case_id") == case.get("case_id") and state.get("attempt_id")==directory.name
                    and (attempt_id==directory.name or legacy_exact)):
                return directory
    fail("CASE_REVISION_SOURCE_INVALID", "无法精确定位原投稿。")


def revisions(pipeline_root, case_id, attempt_id):
    directory = attempt_root(pipeline_root, case_id, attempt_id)
    if any(not (p.parent / "revision_v1.json").is_file()
           for p in (directory / "human_revisions").glob("*/edit_v1.json")):
        fail("CASE_REVISION_SAVE_RECOVERY_REQUIRED", "修改已保存，需恢复原保存操作，不能批准旧候选。")
    records = [(p, read(p)) for p in (directory / "human_revisions").glob("*/revision_v1.json")]
    records.sort(key=lambda pair: pair[1].get("sequence", 0))
    parent = None
    for number, (path, value) in enumerate(records, 1):
        if (value.get("schema_version") != REVISION_VERSION or value.get("sequence") != number
                or value.get("case_id") != case_id or value.get("attempt_id") != attempt_id
                or value.get("revision_id") != path.parent.name or value.get("parent_revision_ref") != parent):
            fail("CASE_REVISION_CHAIN_INVALID", "修订版本链不完整，不能回退批准旧版本。")
        edit=read(check_ref(pipeline_root, value["edit_ref"]))
        if edit.get('schema_version')!=EDIT_VERSION or any(edit.get(k)!=value.get(k) for k in
                ('case_id','attempt_id','revision_id','operation_id','sequence','parent_revision_ref','actor','saved_at')):
            fail('CASE_REVISION_CHAIN_INVALID','人工修订与版本收据不属于同一操作。')
        parent = ref(pipeline_root, path)
    return records


@dataclass(frozen=True)
class EvidenceTarget:
    attempt_root: Path
    original_candidate: Path
    candidate: Path | None
    state: str
    revision_root: Path | None = None
    revision_ref: dict | None = None
    validation_ref: dict | None = None


def resolve_target(pipeline_root, case_id, attempt_id, *, require_valid=False):
    directory, original, attempt = original_target(pipeline_root, case_id, attempt_id)
    terminal=attempt.get('status')=='rejected' or (directory/'human_review_decision_v1.json').exists()
    if require_valid and terminal:
        fail('CASE_REVISION_TERMINAL','该投稿已经结束，不能重新批准。')
    records = revisions(pipeline_root, case_id, attempt_id)
    if not records:
        return EvidenceTarget(directory, original, original, "original")
    path, value = records[-1]
    validation = path.parent / "validation_receipt_v1.json"
    candidate = None
    state = "saved"
    validation_ref = None
    if validation.is_file():
        receipt = read(validation)
        if (receipt.get("schema_version") != VALIDATION_VERSION
                or receipt.get("revision_ref") != ref(pipeline_root, path)
                or receipt.get("edit_ref") != value["edit_ref"]
                or receipt.get("inputs") != read(check_ref(pipeline_root, value["edit_ref"]))["source_refs"]):
            fail("CASE_REVISION_VALIDATION_STALE", "修订校验不属于当前版本。")
        for key,reference in receipt["inputs"].items():
            # Terminal history is not an executable candidate. Rejection's
            # existing retention owner may remove transient media; JSON/SHA
            # history remains readable without re-authorizing those bytes.
            if terminal and key=='video' and not io_path(within(pipeline_root.parent,reference['path'])).is_file():
                continue
            check_ref(pipeline_root.parent, reference)
        for reference in receipt["outputs"].values():
            check_ref(pipeline_root, reference)
        for reference in receipt["tool_refs"].values():
            check_ref(pipeline_root, reference)
        candidate = check_ref(pipeline_root, receipt["candidate_ref"])
        if not candidate.is_relative_to(path.parent):
            fail("CASE_REVISION_VALIDATION_STALE", "派生候选不在当前修订中。")
        validation_ref = ref(pipeline_root, validation)
        state = "validated"
    else:
        executions = sorted(path.parent.glob("r*/result.json"))
        if executions:
            state = "failed" if read(executions[-1]).get("status") == "failed" else "pending"
        elif (path.parent / "build_execution_v1.json").exists():
            state = "pending"
    if require_valid and candidate is None:
        fail("CASE_REVISION_NOT_VALIDATED", "修改已保存，等待重新校验；不能批准旧分析结果。")
    return EvidenceTarget(directory, original, candidate, state, path.parent, ref(pipeline_root, path), validation_ref)


def source_refs(pipeline_root, candidate_path):
    """Hash actual sources once. No caller-provided paths or validation booleans."""
    pipeline_root = Path(pipeline_root).resolve()
    case = read(candidate_path)
    sources = {"candidate": ref(pipeline_root.parent, candidate_path)}
    for key, value in case.get("source_artifacts", {}).items():
        if isinstance(value, str) and Path(value).suffix.lower() == ".json":
            sources[key] = ref(pipeline_root.parent, value)
            recorded=(case.get('provenance',{}).get(key) or {}).get('sha256')
            if recorded and recorded!=sources[key]['sha256']:
                fail('CASE_REVISION_SOURCE_STALE','候选引用的证据字节已变化，不能采用旧校验。')
    video = (case.get("source_evidence", {}).get("video") or {})
    media = ref(pipeline_root.parent, video.get("path", ""))
    recorded = video.get("sha256") or case.get("source_provenance", {}).get("recorded_source_media_sha256")
    if recorded != media["sha256"]:
        fail("CASE_REVISION_SOURCE_STALE", "原视频与已记录的来源 SHA 不一致。")
    sources["video"] = media
    for key in ("audio_v1", "narration_review_v1", "visual_manifest", "visual_v1", "shot_boundaries", "privacy_projection_v1", "storyboard_v1"):
        if key not in sources:
            fail("CASE_REVISION_SOURCE_UNAVAILABLE", "历史分析缺少修订所需的准确证据，请重新分析。")
    return sources


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail("CASE_REVISION_TIMELINE_INVALID", "视频时间无效。")
    return float(value)


def normalize_edits(pipeline_root, sources, narration_edits, boundary_edits):
    repo = Path(pipeline_root).resolve().parent
    audio, narration, manifest, visual, shots = [read(check_ref(repo, sources[k])) for k in (
        "audio_v1", "narration_review_v1", "visual_manifest", "visual_v1", "shot_boundaries")]
    # An edit may resolve known recognition/cut uncertainty, never erase an
    # unsupported source/Proof/privacy risk by asking a fresh model to omit it.
    if (any(s.get('risk_codes') for s in narration.get('segments',[]))
            or any(i.get('risk_codes') for i in narration.get('manual_review',{}).get('items',[]))
            or any(s.get('boundary',{}).get('reason_type') not in KNOWN_BOUNDARY_REASONS for s in shots.get('shots',[]))
            or any(i.get('type') not in {'selected_non_high_confidence_boundary','short_shot'}
                for i in shots.get('manual_review',{}).get('items',[]))):
        fail('CASE_REVISION_RISK_UNRESOLVED','存在尚未解释的来源或证据风险，请补证、重新分析或不收录，不能用文字或切点修改消除风险。')
    duration = _number(manifest.get("duration_seconds"))
    if duration <= 0:
        fail("CASE_REVISION_TIMELINE_INVALID", "缺少有效媒体时长。")
    frame_times = {str(f.get("frame_id") or f["filename"]): _number(f["timestamp_seconds"]) for f in manifest.get("frames", [])}
    observed = {str(f["frame_id"]) for f in visual.get("frames", [])}
    available = {f: t for f, t in frame_times.items() if f in observed and 0 <= t < duration}
    segments = {str(s["segment_id"]): s for s in audio.get("segments", [])}
    reviewed = {str(s["segment_id"]): s for s in narration.get("segments", [])}
    normalized_narration, normalized_boundaries = [], []
    seen = set()
    for row in narration_edits:
        if not isinstance(row, dict) or set(row) != {"segment_id", "corrected_text", "basis", "evidence_frame_refs"}:
            fail("CASE_REVISION_EDIT_INVALID", "口播修订只能提交片段、文字及原声来源。")
        identity = row["segment_id"]
        if identity not in segments or identity not in reviewed or identity in seen:
            fail("CASE_REVISION_SEGMENT_INVALID", "口播片段不存在或重复。")
        seen.add(identity)
        segment = segments[identity]
        start, end = _number(segment["start"]), _number(segment["end"])
        text, frames = row["corrected_text"], row["evidence_frame_refs"]
        if (row["basis"] != "source_audio_listening" or not isinstance(text, str) or not text.strip()
                or len(text) > 4000 or not segment.get("word_refs") or not 0 <= start < end <= duration
                or not isinstance(frames, list) or not frames or len(frames) != len(set(frames))
                or any(f not in available for f in frames)):
            fail("CASE_REVISION_EDIT_INVALID", "请对照原声和合法画面修正，不能新增无来源口播。")
        normalized_narration.append({**row, "original": {k: segment.get(k) for k in
            ("segment_id", "start", "end", "word_refs", "source_text")},
            "previous_reviewed_text": reviewed[identity].get("reviewed_text")})
    starts = [s for s in shots.get("shots", [])]
    selected = {s["boundary"]["selected_from_frame_ref"]: _number(s["start"]) for s in starts}
    if not starts or _number(starts[0]["start"]) != 0:
        fail("CASE_REVISION_TIMELINE_INVALID", "原时间线缺少合法视频起点。")
    first = starts[0]["boundary"]["selected_from_frame_ref"]
    moved = {}
    for row in boundary_edits:
        if not isinstance(row, dict) or set(row) != {"boundary_frame_id", "target_frame_id"}:
            fail("CASE_REVISION_EDIT_INVALID", "分镜修订必须选择已验证的画面，不能提交任意秒数。")
        old, new = row["boundary_frame_id"], row["target_frame_id"]
        if old not in selected or old == first or old in moved or new not in available or new == old:
            fail("CASE_REVISION_BOUNDARY_INVALID", "切点不可移动或目标画面不合法。")
        moved[old] = new
        normalized_boundaries.append({**row, "original_seconds": selected[old], "target_seconds": available[new]})
    times = [available[moved[f]] if f in moved else t for f, t in selected.items()]
    if any(b <= a or b-a < 0.5 for a,b in zip(times, times[1:]+[duration])):
        fail("CASE_REVISION_TIMELINE_INVALID", "切点必须有序、唯一并符合最短片段规则。")
    return normalized_narration, normalized_boundaries


def _pending_final_commands(pipeline_root, case_id):
    for path in (Path(pipeline_root) / "data/review_operations/case" / case_id).glob("*/intent.json"):
        intent = read(path).get("intent", {})
        if intent.get("payload", {}).get("decision") in {"approve", "reject", "reanalyze"} and not (path.parent / "result.json").exists():
            fail("CASE_REVISION_FINAL_COMMAND_PENDING", "已有未结束的审核提交，请先恢复或取消该操作。")


def save_revision(pipeline_root, case_id, attempt_id, *, operation_id, actor, database_path,
                  expected_candidate_sha256, expected_sources_sha256, expected_revision_sha256,
                  narration_edits, boundary_edits, reason="", saved_at=None, validate_only=False):
    """Caller holds Case + reviewer locks. Replays compare ALL immutable inputs."""
    from case_console_authorization_v1 import validate_console_reviewer
    authorization = validate_console_reviewer(database_path, actor["user_id"], actor["namespace"])
    if not isinstance(operation_id, str) or not OPERATION.fullmatch(operation_id):
        fail("CASE_REVISION_ID_INVALID", "修订操作身份无效。")
    pipeline_root = Path(pipeline_root).resolve()
    directory, original, state = original_target(pipeline_root, case_id, attempt_id)
    terminal=(state.get("status") != "awaiting_review" or (directory / "human_review_decision_v1.json").exists()
        or (pipeline_root / "data/cases" / case_id / "approval_receipt.json").exists())
    revision_id = "revision_" + operation_id
    revision_root = directory / "human_revisions" / revision_id
    # A lost response is recoverable before CAS, but is never a different edit.
    edit_path = revision_root / "edit_v1.json"
    request = {"actor": actor, "expected_candidate_sha256": expected_candidate_sha256,
        "expected_sources_sha256": expected_sources_sha256, "expected_revision_sha256": expected_revision_sha256,
        "narration_edits": narration_edits, "boundary_edits": boundary_edits, "reason": reason}
    if edit_path.exists():
        edit = read(edit_path)
        if edit.get("request_sha256") != digest(request):
            fail("CASE_REVISION_REPLAY_CONFLICT", "原修订操作已绑定其他来源、审核人或内容。")
        for reference in edit["source_refs"].values():
            if (terminal and reference==edit['source_refs'].get('video')
                    and not io_path(within(pipeline_root.parent,reference['path'])).is_file()
                    and (read(original).get('source_evidence',{}).get('video',{}).get('sha256')==reference['sha256'])):
                continue
            check_ref(pipeline_root.parent, reference)
        recorded=revision_root/'revision_v1.json'
        if recorded.exists():
            # A delayed response belongs to THIS saved operation, even if a
            # newer revision or final approval now exists. Never adopt the head
            # as its result or enqueue the head under the older operation ID.
            value=read(recorded)
            if value.get('edit_ref')!=ref(pipeline_root,edit_path) or any(value.get(k)!=edit.get(k) for k in
                    ('case_id','attempt_id','revision_id','operation_id','actor','parent_revision_ref')):
                fail('CASE_REVISION_REPLAY_CONFLICT','原保存收据与本次操作不一致。')
            return EvidenceTarget(directory,original,None,'saved',revision_root,ref(pipeline_root,recorded))
        if terminal:
            fail('CASE_REVISION_TERMINAL','已结束的案例不能补建新的编辑版本。')
        parent = edit["parent_revision_ref"]
        sequence = edit["sequence"]
    else:
        if terminal:
            fail("CASE_REVISION_TERMINAL", "已结束的案例不能继续修改，请保留历史并发起合法新分析。")
        _pending_final_commands(pipeline_root, case_id)
        target = resolve_target(pipeline_root, case_id, attempt_id, require_valid=True)
        parent = target.revision_ref
        if (parent or {}).get("sha256") != expected_revision_sha256:
            fail("CASE_REVISION_HEAD_STALE", "已有更新修订，请刷新后再修改。")
        if file_sha(target.candidate) != expected_candidate_sha256:
            fail("CASE_REVISION_SOURCE_STALE", "候选已变化，请刷新后核对。")
        sources = source_refs(pipeline_root, target.candidate)
        if digest(sources) != expected_sources_sha256:
            fail("CASE_REVISION_SOURCE_STALE", "原始证据已变化，请刷新后核对。")
        narration, boundaries = normalize_edits(pipeline_root, sources, narration_edits, boundary_edits)
        if not narration and not boundaries:
            fail("CASE_REVISION_EDIT_INVALID", "没有需要保存的修改。")
        sequence = len(revisions(pipeline_root, case_id, attempt_id)) + 1
        edit = {"schema_version": EDIT_VERSION, "case_id": case_id, "attempt_id": attempt_id,
            "revision_id": revision_id, "operation_id": operation_id, "sequence": sequence,
            "parent_revision_ref": parent, "source_refs": sources,
            "original_candidate_ref": ref(pipeline_root, original), "actor": actor,
            "authorization": authorization, "saved_at": saved_at or datetime.now(timezone.utc).isoformat(),
            "narration_edits": narration, "boundary_edits": boundaries, "reason": reason,
            "request_sha256": digest(request)}
        if validate_only:
            return target
        write_once(edit_path, edit)
    revision = {"schema_version": REVISION_VERSION, "case_id": case_id, "attempt_id": attempt_id,
        "revision_id": revision_id, "operation_id": operation_id, "sequence": sequence,
        "parent_revision_ref": parent, "edit_ref": ref(pipeline_root, edit_path),
        "actor": actor, "saved_at": edit["saved_at"]}
    write_once(revision_root / "revision_v1.json", revision)
    return resolve_target(pipeline_root, case_id, attempt_id)


def bind_build_execution(pipeline_root, database_path, case_id, attempt_id, revision_id, task_id):
    """A genuine Case-analysis execution is distinct from the original Attempt."""
    import json
    import sqlite3
    root = attempt_root(pipeline_root, case_id, attempt_id)
    if not re.fullmatch(r"revision_[a-f0-9]{32}", revision_id):
        fail("CASE_REVISION_ID_INVALID", "修订身份无效。")
    revision = root / "human_revisions" / revision_id / "revision_v1.json"
    value = read(revision)
    with sqlite3.connect(Path(database_path).resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        task = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not task:
        fail("CASE_REVISION_EXECUTION_INVALID", "修订计算任务不存在。")
    payload = json.loads(task["payload_json"])
    expected = {"attempt_id":attempt_id, "revision_id":revision_id, "revision_sha256":file_sha(revision)}
    if (task["task_type"] != "case_analysis" or task["subject_ref"] != case_id
            or task["created_by_user_id"] != value["actor"]["user_id"]
            or payload.get("evidence_revision") != expected or payload.get("review_operation_id") != value["operation_id"]):
        fail("CASE_REVISION_EXECUTION_INVALID", "修订不能借用其他 Task 或投稿身份。")
    execution = {"schema_version":"case-human-evidence-build-execution-v1.0", "case_id":case_id,
        "attempt_id":attempt_id, "revision_ref":ref(pipeline_root,revision), "build_task_id":task_id}
    write_once(revision.parent / "build_execution_v1.json", execution)
    return execution


def _validate_derived(pipeline_root, edit, candidate):
    """Recheck actual bytes/structure, not a user-supplied `passed` value."""
    from privacy_projection_v1 import validate_case_privacy_gate, scan_sensitive_values
    pipeline_root = Path(pipeline_root).resolve()
    case = read(candidate)
    source = edit["source_refs"]
    for reference in source.values():
        check_ref(pipeline_root.parent, reference)
    if (case.get("case_id") != edit["case_id"] or case.get("analysis_lineage", {}).get("attempt_id") != edit["attempt_id"]
            or case.get("lifecycle", {}).get("approved") is not False or case.get("validation", {}).get("auto_approved") is not False):
        fail("CASE_REVISION_VALIDATION_FAILED", "派生候选身份或生命周期错误。")
    validate_case_privacy_gate(case)
    paths = {k:within(pipeline_root, v) for k,v in case["source_artifacts"].items() if isinstance(v,str) and v.endswith('.json')}
    audio, narration, manifest, visual, shots, board = [read(paths[k]) for k in
        ("audio_v1","narration_review_v1","visual_manifest","visual_v1","shot_boundaries","storyboard_v1")]
    raw = read(check_ref(pipeline_root.parent, source["audio_v1"]))
    if audio != raw:
        fail("CASE_REVISION_VALIDATION_FAILED", "修订不得改写原 ASR 或词时间。")
    words = [w["word_id"] for w in raw["words"]]
    frames = [f["frame_id"] for f in visual["frames"]]
    corrected = {r["segment_id"]:r["corrected_text"] for r in edit["narration_edits"]}
    if len(narration["segments"]) != len(raw["segments"]):
        fail("CASE_REVISION_VALIDATION_FAILED", "口播片段数量变化。")
    for original, effective in zip(raw["segments"], narration["segments"]):
        if any(original.get(k) != effective.get(k) for k in ("segment_id","start","end","word_refs","source_text")):
            fail("CASE_REVISION_VALIDATION_FAILED", "原声时间或词来源变化。")
        if effective["segment_id"] in corrected and (effective["reviewed_text"] != corrected[effective["segment_id"]]
                or effective.get("explicit_review", {}).get("action") != "correct"):
            fail("CASE_REVISION_VALIDATION_FAILED", "修订文字未进入正式口播投影。")
    if ([w for s in shots["shots"] for w in s["audio_projection"]["word_refs"]] != words
            or [f for s in shots["shots"] for f in s["visual_projection"]["frame_refs"]] != frames):
        fail("CASE_REVISION_VALIDATION_FAILED", "画面或原词不是按序唯一覆盖。")
    times = [float(s["start"]) for s in shots["shots"]]
    duration = float(manifest["duration_seconds"])
    if not times or times[0] != 0 or any(b <= a for a,b in zip(times,times[1:]+[duration])):
        fail("CASE_REVISION_VALIDATION_FAILED", "派生时间线不合法。")
    for index,shot in enumerate(shots["shots"]):
        if float(shot["end"]) != (times[index+1] if index+1<len(times) else duration):
            fail("CASE_REVISION_VALIDATION_FAILED", "派生时间线有空段或重叠。")
    for change in edit["boundary_edits"]:
        if change["target_seconds"] not in times or change["original_seconds"] in times:
            fail("CASE_REVISION_VALIDATION_FAILED", "目标切点未进入正式分镜投影。")
    previous_shots = read(check_ref(pipeline_root.parent,source['shot_boundaries']))['shots']
    moved = {r['boundary_frame_id']:r['target_frame_id'] for r in edit['boundary_edits']}
    expected_frames = [moved.get(s['boundary']['selected_from_frame_ref'],s['boundary']['selected_from_frame_ref']) for s in previous_shots]
    if [s['boundary']['selected_from_frame_ref'] for s in shots['shots']] != expected_frames:
        fail("CASE_REVISION_VALIDATION_FAILED", "重算改变了本次未授权调整的切点，需要重新核对。")
    if [s["shot_id"] for s in board["shots"]] != [s["shot_id"] for s in shots["shots"]]:
        fail("CASE_REVISION_VALIDATION_FAILED", "Storyboard 未跟随新分镜重新派生。")
    if [s["segment_id"] for s in board["narration_track"]] != [s["segment_id"] for s in narration["segments"]]:
        fail("CASE_REVISION_VALIDATION_FAILED", "Storyboard 未跟随新口播重新派生。")
    if scan_sensitive_values({"human_corrected_text":[r["corrected_text"] for r in edit["narration_edits"]]}):
        fail("CASE_REVISION_PRIVACY_REQUIRED", "人工文字含待处理的隐私风险，不能直接批准。")
    for key in ("narration_review_v1","shot_boundaries","storyboard_v1","privacy_projection_v1"):
        if read(paths[key]).get("validation",{}).get("passed") is not True:
            fail("CASE_REVISION_VALIDATION_FAILED", "派生校验未通过。")
    return paths


def derive_revision(pipeline_root, database_path, case_id, attempt_id, revision_id, task_id, run_command):
    """Reuse the real builders; only their external model transports may be synthetic.

    Every retry writes a fresh run directory. No historical `passed` cache is
    reused. A validation receipt is published only after the whole graph passes.
    Caller holds Case/reviewer locks, using the existing Case Task lifecycle.
    """
    import sys
    from case_console_authorization_v1 import validate_console_reviewer
    pipeline_root = Path(pipeline_root).resolve()
    binding = bind_build_execution(pipeline_root,database_path,case_id,attempt_id,revision_id,task_id)
    revision_path = check_ref(pipeline_root,binding["revision_ref"])
    target = resolve_target(pipeline_root,case_id,attempt_id)
    if target.revision_ref != binding["revision_ref"]:
        fail("CASE_REVISION_HEAD_STALE", "计算任务不属于最新修订。")
    if target.state == "validated":
        return target
    _,_,original_state=original_target(pipeline_root,case_id,attempt_id)
    if (original_state.get('status')!='awaiting_review' or (target.attempt_root/'human_review_decision_v1.json').exists()
            or (pipeline_root/'data/cases'/case_id/'approval_receipt.json').exists()):
        fail('CASE_REVISION_TERMINAL','已结束的案例不能继续生成编辑候选。')
    edit_path = check_ref(pipeline_root,read(revision_path)["edit_ref"])
    edit = read(edit_path)
    validate_console_reviewer(database_path,edit["actor"]["user_id"],edit["actor"]["namespace"])
    source_paths = {k:check_ref(pipeline_root.parent,v) for k,v in edit["source_refs"].items()}
    prior = read(source_paths["candidate"])
    root = revision_path.parent
    run_number = len(list(root.glob('r*/intent.json'))) + 1
    work = root/f'r{run_number:04d}'
    scripts = pipeline_root/'scripts'
    tools = {name:ref(pipeline_root,scripts/name) for name in ('build_privacy_projection_v1.py',
        'build_narration_review_v1.py','build_shot_boundaries_v1.py','generate_reverse_storyboard.py','build_case_v1.py')}
    cache_key = digest({"revision":binding["revision_ref"],"edit":ref(pipeline_root,edit_path),"sources":edit["source_refs"],"tools":tools})
    write_once(work/'intent.json',{"binding":binding,"cache_key":cache_key,"tool_refs":tools})
    def invoke(name, arguments, timeout=1800, model=False):
        # Existing builders use pathlib throughout. Extended IO paths permit
        # their immutable chunk evidence on Windows without relocating lineage.
        values=[str(io_path(v)) if isinstance(v,Path) else str(v) for v in arguments]
        run_command(name,[sys.executable,str(scripts/name),*values],"structure",timeout,needs_deepseek=model)
    try:
        privacy = work/'p/privacy_projection_v1.json'
        invoke('build_privacy_projection_v1.py',['--case-id',case_id,'--visual-v1',source_paths['visual_v1'],
            '--audio-v1',source_paths['audio_v1'],'--human-evidence-edit',edit_path,'--output-root',privacy.parent],300)
        # Merge prior human corrections without mutating the original ASR.
        inherited = {}
        previous = read(source_paths['narration_review_v1'])
        for item in previous.get('segments',[]):
            if item.get('explicit_review',{}).get('action')=='correct':
                inherited[item['segment_id']]={"segment_id":item['segment_id'],"action":"correct",
                    "corrected_text":item['reviewed_text'],"evidence_frame_refs":item['evidence_frame_refs']}
        for item in edit['narration_edits']:
            inherited[item['segment_id']]={"segment_id":item['segment_id'],"action":"correct",
                "corrected_text":item['corrected_text'],"evidence_frame_refs":item['evidence_frame_refs']}
        narration_input = work/'narration_review_input.json'
        if inherited:
            write_once(narration_input,{"case_id":case_id,"reviewer":edit['actor'],"decisions":list(inherited.values()),"human_edit_ref":ref(pipeline_root,edit_path)})
        narration = work/'n/narration_review_v1.json'
        args=['--case-id',case_id,'--audio-v1',source_paths['audio_v1'],'--visual-v1',source_paths['visual_v1'],
            '--privacy-projection',privacy,'--output-root',narration.parent]
        if inherited: args += ['--review-file',narration_input]
        invoke('build_narration_review_v1.py',args,model=True)
        # Existing selected boundaries are preserved; moving one is reject(old)
        # + keep(verified target). The builder still validates exact-once/order.
        old_shots = read(source_paths['shot_boundaries'])
        moves={r['boundary_frame_id']:r['target_frame_id'] for r in edit['boundary_edits']}
        decisions=[]
        for shot in old_shots['shots']:
            frame=shot['boundary']['selected_from_frame_ref']
            if frame in moves:
                decisions.extend([{"frame_id":frame,"action":"reject"},{"frame_id":moves[frame],"action":"keep"}])
        shot_input=work/'boundary_review_input.json'
        if decisions: write_once(shot_input,{"case_id":case_id,"decisions":decisions,"human_edit_ref":ref(pipeline_root,edit_path)})
        shots=work/'s/shot_boundaries_v1_1.json'
        args=['--case-id',case_id,'--visual-v1',source_paths['visual_v1'],'--visual-manifest',source_paths['visual_manifest'],
            '--audio-v1',source_paths['audio_v1'],'--privacy-projection',privacy,'--output-root',shots.parent]
        if decisions: args += ['--review-file',shot_input]
        invoke('build_shot_boundaries_v1.py',args,model=True)
        pending=any(read(p).get('manual_review',{}).get('required') is True for p in (narration,shots))
        board=work/'b/reverse_storyboard_v1.json'
        args=['--shot-boundaries',shots,'--audio-v1',source_paths['audio_v1'],'--narration-review',narration,
            '--privacy-projection',privacy,'--output-root',board.parent]
        if pending: args.append('--defer-manual-review')
        invoke('generate_reverse_storyboard.py',args,2400,model=True)
        candidate=work/'c'/case_id/'case_v1.json'
        args=['--case-id',case_id,'--industry',prior['identity'].get('industry','待分类'),
            '--video',source_paths['video'],'--audio-v1',source_paths['audio_v1'],'--narration-review',narration,
            '--visual-manifest',source_paths['visual_manifest'],'--visual-v1',source_paths['visual_v1'],
            '--shot-boundaries',shots,'--storyboard-v1',board,'--privacy-projection',privacy,
            '--source-url',prior['identity']['source_url'],'--output-root',candidate.parent.parent]
        if pending: args.append('--defer-manual-review')
        if prior.get('operator_profile_hint'): args += ['--operator-profile-hint',prior['operator_profile_hint']]
        elif prior['identity'].get('analysis_profile'): args += ['--profile',prior['identity']['analysis_profile']]
        invoke('build_case_v1.py',args,600)
        case=read(candidate)
        def logical_paths(value):
            if isinstance(value,dict): return {k:logical_paths(v) for k,v in value.items()}
            if isinstance(value,list): return [logical_paths(v) for v in value]
            return value[4:] if isinstance(value,str) and value.startswith('\\\\?\\') else value
        case=logical_paths(case)
        for key in ('analysis_lineage','source_governance','source_provenance'):
            if key in prior: case[key]=prior[key]
        for key in ('source_acquisition_v1','source_metadata_v1'):
            if key in prior['source_artifacts']: case['source_artifacts'][key]=prior['source_artifacts'][key]
        case['source_evidence']['video']=prior['source_evidence']['video']
        if prior['source_evidence'].get('cover'): case['source_evidence']['cover']=prior['source_evidence']['cover']
        case['human_evidence_revision']={"revision_ref":ref(pipeline_root,revision_path),"edit_ref":ref(pipeline_root,edit_path)}
        # Builder output is still an unpublished derived draft. Finalize lineage
        # before hashing/publication; no original/model artifact is overwritten.
        candidate.write_text(__import__('json').dumps(case,ensure_ascii=False,indent=2),encoding='utf-8')
        paths=_validate_derived(pipeline_root,edit,candidate)
        validate_console_reviewer(database_path,edit['actor']['user_id'],edit['actor']['namespace'])
        receipt={"schema_version":VALIDATION_VERSION,"revision_ref":ref(pipeline_root,revision_path),
            "edit_ref":ref(pipeline_root,edit_path),"execution_ref":ref(pipeline_root,work/'intent.json'),
            "cache_key":cache_key,"inputs":edit['source_refs'],"tool_refs":tools,
            "outputs":{k:ref(pipeline_root,v) for k,v in paths.items()},"candidate_ref":ref(pipeline_root,candidate),
            "validated_at":datetime.now(timezone.utc).isoformat()}
        write_once(root/'validation_receipt_v1.json',receipt)
        write_once(work/'result.json',{"status":"validated","validation_ref":ref(pipeline_root,root/'validation_receipt_v1.json')})
    except Exception as exc:
        if not (work/'result.json').exists():
            write_once(work/'result.json',{"status":"failed","code":getattr(exc,'code','CASE_REVISION_BUILD_FAILED'),
                "message":str(exc),"at":datetime.now(timezone.utc).isoformat()})
        raise
    return resolve_target(pipeline_root,case_id,attempt_id,require_valid=True)


def review_scope(pipeline_root, case_id, attempt_id):
    """Deterministic risk policy. Unknown/source/privacy failures never bulk keep."""
    from privacy_projection_v1 import validate_case_privacy_gate
    target = resolve_target(pipeline_root,case_id,attempt_id,require_valid=True)
    candidate = target.candidate
    case = read(candidate)
    from approve_case_v1 import validate_source_provenance
    _, errors=validate_source_provenance(case)
    if errors:
        fail('CASE_REVISION_SOURCE_INVALID','原始来源尚未完整核对，不能批量确认。')
    sources = source_refs(pipeline_root,candidate)
    validate_case_privacy_gate(case)
    repo = Path(pipeline_root).resolve().parent
    audio,narration,manifest,visual,shots = [read(check_ref(repo,sources[k])) for k in
        ('audio_v1','narration_review_v1','visual_manifest','visual_v1','shot_boundaries')]
    duration = _number(manifest.get('duration_seconds'))
    frames = {f.get('frame_id') or f['filename']:_number(f['timestamp_seconds']) for f in manifest['frames']}
    observed = {f['frame_id'] for f in visual['frames']}
    raw = {s['segment_id']:s for s in audio['segments']}
    original_case=read(target.original_candidate)
    original_narration=read(within(pipeline_root,original_case['source_artifacts']['narration_review_v1']))
    original_shots=read(within(pipeline_root,original_case['source_artifacts']['shot_boundaries']))
    inherited_narration_risks={s['segment_id'] for s in original_narration.get('segments',[]) if
        s.get('confidence')!='high' or s.get('decision') not in {'unchanged','keep'} or s.get('low_confidence_words')}
    inherited_narration_risks.update(i['segment_id'] for i in original_narration.get('manual_review',{}).get('items',[]))
    inherited_shot_risks={s['boundary']['selected_from_frame_ref'] for s in original_shots.get('shots',[]) if
        s['boundary'].get('confidence')!='high' or s['boundary'].get('reason_type')=='uncertain'}
    inherited_shot_risks.update(i.get('frame_id') or i.get('boundary_frame_id') for i in original_shots.get('manual_review',{}).get('items',[]))
    corrections, moved, boundary_origins = {}, {}, {}
    for _, revision in revisions(pipeline_root,case_id,attempt_id):
        edit = read(check_ref(pipeline_root,revision['edit_ref']))
        for row in edit['narration_edits']: corrections[row['segment_id']]=revision['edit_ref']
        for row in edit['boundary_edits']:
            origin=boundary_origins.pop(row['boundary_frame_id'],row['boundary_frame_id'])
            boundary_origins[row['target_frame_id']]=origin
            moved[row['boundary_frame_id']]=revision['edit_ref']
            moved[row['target_frame_id']]=revision['edit_ref']
    rows=[]
    pending_n={i['segment_id']:i for i in narration.get('manual_review',{}).get('items',[])}
    pending_s={i.get('frame_id') or i.get('boundary_frame_id'):i for i in shots.get('manual_review',{}).get('items',[])}
    def add(kind,identity,mode,reasons,**display):
        rows.append({'item_id':kind+':'+identity,'kind':kind,'source_id':identity,'mode':mode,
            'risk_codes':reasons,**display})
    for segment in narration['segments']:
        identity=segment['segment_id'];original=raw.get(identity)
        mode,reasons='ordinary',[]
        start,end=_number(segment['start']),_number(segment['end'])
        if (not original or not 0<=start<end<=duration
                or any(original.get(k)!=segment.get(k) for k in ('start','end','word_refs','source_text'))):
            mode,reasons='blocked',['source_or_timeline_conflict']
        elif identity in corrections and target.validation_ref:
            mode='resolved_by_revision'
        elif (identity in pending_n or identity in inherited_narration_risks or segment.get('confidence')!='high' or segment.get('low_confidence_words')
                or segment.get('reviewed_text')!=segment.get('source_text') or segment.get('decision') not in {'unchanged','keep'}):
            mode,reasons='explicit',['uncertain_recognition']
        if segment.get('risk_codes') or (pending_n.get(identity) or {}).get('risk_codes'):
            mode,reasons='blocked',['unhandled_risk_type']
        add('narration',identity,mode,reasons,start=start,end=end,original_text=original.get('source_text','') if original else '',
            effective_text=segment.get('reviewed_text',''),revision_edit_ref=corrections.get(identity))
    for shot in shots['shots']:
        boundary=shot['boundary'];identity=boundary['selected_from_frame_ref'];start=_number(shot['start']);end=_number(shot['end'])
        mode,reasons='ordinary',[]
        risk=pending_s.get(identity)
        if identity not in observed or identity not in frames or frames[identity]!=start or not 0<=start<end<=duration:
            mode,reasons='blocked',['source_or_timeline_conflict']
        elif identity in moved and target.validation_ref:
            mode='resolved_by_revision'
        elif risk or identity in inherited_shot_risks or boundary.get('confidence')!='high' or boundary.get('reason_type')=='uncertain':
            mode,reasons='explicit',['uncertain_boundary']
        if boundary.get('reason_type') not in KNOWN_BOUNDARY_REASONS:
            mode,reasons='blocked',['unhandled_risk_type']
        if risk and risk.get('type') not in {'selected_non_high_confidence_boundary','short_shot'}:
            mode,reasons='blocked',['unhandled_risk_type']
        add('shot',identity,mode,reasons,start=start,end=end,revision_edit_ref=moved.get(identity))
    # No unrecognised pending item may disappear outside the displayed scope.
    known={(r['kind'],r['source_id']) for r in rows}
    for kind,pending in (('narration',pending_n),('shot',pending_s)):
        for identity in pending:
            if (kind,identity) not in known:
                add(kind,identity,'blocked',['unhandled_pending_item'])
    value={'schema_version':POLICY_VERSION,'case_id':case_id,'attempt_id':attempt_id,
        'candidate_sha256':file_sha(candidate),'original_candidate_sha256':file_sha(target.original_candidate),
        'revision_ref':target.revision_ref,'validation_ref':target.validation_ref,
        'sources_sha256':digest(sources),'items':rows,
        'summary':{'keep_original':sum(r['mode'] in {'ordinary','explicit'} for r in rows),
            'ordinary':sum(r['mode']=='ordinary' for r in rows),'explicit':sum(r['mode']=='explicit' for r in rows),
            'blocked':sum(r['mode']=='blocked' for r in rows),'corrected_narration':len(corrections),
            'adjusted_boundaries':len(set(boundary_origins.values()))}}
    return {**value,'scope_sha256':digest(value)}


def require_confirmation_contract(context, submission):
    """Command version, never a nullable scope, selects the frozen contract."""
    if context is None or context.get('version') == 'human-review-command-v1.0':
        return  # Trusted offline or genuine historical context; existing v1 Gates still apply.
    if context.get('version') not in {'human-review-command-v1.1','human-review-command-v1.2','human-review-command-v1.6'}:
        fail('CASE_EVIDENCE_SCOPE_STALE', '审核上下文版本不受支持，请重新打开页面。')
    snapshot = context.get('snapshot') or {}
    scope_sha = snapshot.get('scope_sha256')
    if not isinstance(scope_sha, str) or not re.fullmatch(r'[a-f0-9]{64}', scope_sha):
        fail('CASE_EVIDENCE_SCOPE_UNAVAILABLE', '当前审核范围无法建立，请恢复完整来源与依赖证据，或重新分析后再批准。')
    if (not isinstance(submission, dict) or submission.get('schema_version') != FINAL_VERSION
            or submission.get('scope_sha256') != scope_sha):
        fail('CASE_EVIDENCE_SCOPE_STALE', '当前新版操作必须确认准确的完整审核范围，不能降级为旧版保留请求。')


def validate_console_confirmation(pipeline_root, case, candidate_sha256, authorization, operation_id, receipt):
    """CLI independently binds Coverage to the existing durable Console command."""
    if not isinstance(operation_id, str) or not OPERATION.fullmatch(operation_id):
        fail('CASE_EVIDENCE_SCOPE_STALE', 'Console 批准必须绑定原正式审核操作。')
    try:
        root = Path(pipeline_root).resolve()
        saved = read(root / 'data/review_operations/case' / case['case_id'] / operation_id / 'intent.json')
        context = saved['context']
        snapshot = context['snapshot']
        intent = saved['intent']
        if (saved['version'] != context['version'] or context['kind'] != 'case'
                or context['identity'] != case['case_id'] or context['operation_id'] != operation_id
                or any(context['actor'].get(k) != authorization.get(k) for k in ('namespace','user_id'))
                or intent['request_path'] != f"/api/cases/{case['case_id']}/review"
                or intent['payload'].get('decision') != 'approve'
                or snapshot['artifact_sha256'] != candidate_sha256
                or file_sha(within(root, snapshot['artifact'])) != candidate_sha256):
            fail('CASE_EVIDENCE_SCOPE_STALE', '审核操作与当前候选或审核人不一致。')
        submission = receipt.get('submission') if isinstance(receipt, dict) else None
        require_confirmation_contract(context, submission)
        if context['version'] in {'human-review-command-v1.1','human-review-command-v1.2','human-review-command-v1.6'} and submission != intent['payload'].get('evidence_review'):
            fail('CASE_EVIDENCE_SCOPE_STALE', '最终确认与原操作提交的审核范围不一致。')
    except RevisionError:
        raise
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        fail('CASE_EVIDENCE_SCOPE_STALE', '无法验证原正式审核操作，不能沿旧版接口批准。')


def final_review(pipeline_root, case_id, attempt_id, submission, *, actor, reviewer, operation_id, reviewed_at):
    scope=review_scope(pipeline_root,case_id,attempt_id)
    if (not isinstance(submission,dict) or set(submission)!={'schema_version','confirmation_mode','scope_sha256','explicit_keep_ids'}
            or submission['schema_version']!=FINAL_VERSION or submission['confirmation_mode']!='final_bulk_keep'
            or submission['scope_sha256']!=scope['scope_sha256']):
        fail('CASE_EVIDENCE_SCOPE_STALE','审核范围已变化，请刷新并核对当前修订。')
    expected={r['item_id'] for r in scope['items'] if r['mode']=='explicit'}
    provided=submission['explicit_keep_ids']
    if (not isinstance(provided,list) or len(provided)!=len(set(provided)) or set(provided)!=expected
            or scope['summary']['blocked']):
        fail('CASE_EVIDENCE_RISK_UNRESOLVED','仍有需要明确处理的疑点，不能统一批准。')
    decisions=[]
    for row in scope['items']:
        resolved=row['mode']=='resolved_by_revision'
        decisions.append({'item_id':row['item_id'],'action':'resolved_by_revision' if resolved else 'keep',
            'origin':'validated_human_revision' if resolved else 'human_explicit_keep' if row['mode']=='explicit' else 'human_final_confirmation',
            'revision_edit_ref':row.get('revision_edit_ref') if resolved else None})
    return {'schema_version':FINAL_VERSION,'case_id':case_id,'attempt_id':attempt_id,
        'candidate_sha256':scope['candidate_sha256'],'original_candidate_sha256':scope['original_candidate_sha256'],
        'revision_ref':scope['revision_ref'],'validation_ref':scope['validation_ref'],'scope_sha256':scope['scope_sha256'],
        'submission':submission,'decisions':decisions,'actor':actor,'reviewed_by':reviewer,
        'operation_id':operation_id,'reviewed_at':reviewed_at}


def validate_final_review(case, candidate_sha256, receipt_path, reviewer):
    """Shared API/CLI coverage owner, including staged copies of the candidate."""
    receipt=read(receipt_path)
    # The receipt lives under the original, exact Attempt. This is a source ref,
    # not the staging directory's shape or an arbitrary client path.
    case_id,attempt_id=receipt['case_id'],receipt['attempt_id']
    root=Path(receipt_path).resolve()
    directory=next((p for p in root.parents if p.name==attempt_id and (p/'case_analysis_attempt_v1.json').is_file()),None)
    if directory is None: fail('CASE_EVIDENCE_SCOPE_STALE','无法定位审核来源。')
    pipeline_root=directory.parents[3]
    target=resolve_target(pipeline_root,case_id,attempt_id,require_valid=True)
    if (candidate_sha256!=file_sha(target.candidate) or case!=read(target.candidate)
            or case['case_id']!=case_id or receipt['reviewed_by']!=reviewer):
        fail('CASE_EVIDENCE_SCOPE_STALE','最终审核不属于当前候选。')
    expected=final_review(pipeline_root,case_id,attempt_id,receipt['submission'],actor=receipt['actor'],
        reviewer=reviewer,operation_id=receipt['operation_id'],reviewed_at=receipt['reviewed_at'])
    if expected!=receipt: fail('CASE_EVIDENCE_SCOPE_STALE','最终审核覆盖不完整或来源已变化。')
    return receipt


def approval_attempt_errors(case, candidate_sha256, case_path):
    """CLI uses the same effective target; historical unbound files stay legacy."""
    lineage=case.get('analysis_lineage') or {}
    try:
        if lineage.get('attempt_artifact'):
            state_path=Path(lineage['attempt_artifact']).resolve()
            state=read(state_path)
            directory=state_path.parent
            if (state_path.name!='case_analysis_attempt_v1.json' or state.get('case_id')!=case.get('case_id')
                    or state.get('attempt_id')!=lineage.get('attempt_id') or directory.name!=state.get('attempt_id')):
                return ['Case Attempt source identity mismatch.']
        else:
            try:directory=root_for_candidate(case_path)
            except RevisionError:return []  # Existing standalone offline contract.
            state=read(directory/'case_analysis_attempt_v1.json')
        if state.get('status')!='awaiting_review' or (directory/'human_review_decision_v1.json').exists():
            return ['Case Attempt is terminal or not ready; it cannot be approved again.']
        target=resolve_target(directory.parents[3],case['case_id'],directory.name,require_valid=True)
        if file_sha(target.candidate)!=candidate_sha256:
            return ['Case candidate is not the current effective Attempt/revision.']
        if target.revision_ref and Path(case_path).resolve()==target.candidate.resolve():
            return ['Immutable revision candidates must be approved through a separate staged Case transaction.']
        return []
    except (OSError,ValueError,KeyError,RuntimeError,TypeError) as exc:
        return [f'Case Attempt/revision cannot be verified: {exc}']
