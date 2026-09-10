from __future__ import annotations

import argparse
import getpass
import re
import json
import hashlib
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI


SCHEMA_VERSION = "reverse-storyboard-v1.1-draft"
INTERPRETATION_PROMPT_VERSION = "reverse-storyboard-v1.1-interpretation"
GLOBAL_UNDERSTANDING_PROMPT_VERSION = (
    "reverse-storyboard-v1.1-global-understanding"
)

RELATION_CANDIDATE_SET = {"开始", "延续", "结束", "完整", "重叠", "无旁白"}

ALLOWED_ROLES = {
    "hook",
    "context",
    "action",
    "persona",
    "product",
    "claim",
    "explanation",
    "emotion",
    "proof",
    "transition",
    "payoff",
    "CTA",
    "other",
}

ALLOWED_RELATIONS = {
    "repeat",
    "reinforce",
    "supplement",
    "independent",
    "conflict",
    "unknown",
}

ALLOWED_PROOF_TYPES = {
    "data",
    "customer_review",
    "before_after",
    "order",
    "dashboard",
    "certificate",
    "physical_result",
    "documented_case_result",
    "other_verifiable",
}

PHONE_PATTERN = re.compile(r"(?:\+?86[- ]?)?1[3-9]\d{9}")
ORDER_NUMBER_PATTERN = re.compile(
    r"(?:订单|订单号|订单编号|运单|运单号|提货码|取餐码|外卖码|取货码|单号)[^\u4e00-\u9fa5A-Za-z0-9]{0,12}[A-Za-z0-9]{4,}",
    re.IGNORECASE,
)
RELEVANT_ADDRESS_PATTERN = re.compile(
    r"(?:地址|收货地址|送货地址|门牌|住址|收件人|顾客姓名|订单信息|订单姓名)",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sanitize_pii_text(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""

    if PHONE_PATTERN.search(text):
        return "电话"

    if ORDER_NUMBER_PATTERN.search(text):
        return "订单标签"

    if RELEVANT_ADDRESS_PATTERN.search(text):
        return "包装上的订单信息"

    if "配送" in text or "快递" in text:
        return "配送标签"

    return text


def sanitize_information_states(
    info_states: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out = []
    for state in info_states:
        item = dict(state)
        item["ocr_raw"] = sanitize_pii_text(item.get("ocr_raw", ""))
        item["scene_summary"] = sanitize_pii_text(item.get("scene_summary", ""))
        out.append(item)

    return out


def stable_hash(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def float_eq(left: float, right: float, tol: float = 1e-6) -> bool:
    return abs(float(left) - float(right)) <= tol


def get_client() -> OpenAI:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        key = getpass.getpass("DeepSeek API Key: ")
    return OpenAI(api_key=key, base_url="https://api.deepseek.com")


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def gpu_name() -> str | None:
    try:
        value = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return value.splitlines()[0].strip() if value else None
    except Exception:
        return None


def uniq_text(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        value = (item or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def normalize_role_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"secondary_roles must be an array, got {type(value)}")
    return [str(x) for x in value]


def build_shot_input(shot: dict[str, Any]) -> dict[str, Any]:
    info_states = sanitize_information_states(
        shot.get("visual_projection", {}).get("information_states", [])
    )

    ocr_sequence = uniq_text(
        [str(x.get("ocr_raw", "")) for x in info_states]
    )

    scene_sequence = uniq_text(
        [str(x.get("scene_summary", "")) for x in info_states]
    )

    visual_refs = [
        str(x) for x in shot.get("visual_projection", {}).get("frame_refs", [])
    ]

    audio = shot.get("audio_projection", {})

    return {
        "shot_id": shot["shot_id"],
        "start": shot["start"],
        "end": shot["end"],
        "duration": shot["duration"],
        "boundary_reason_type": shot.get("boundary", {}).get("reason_type"),
        "boundary_reason": shot.get("boundary", {}).get("reason"),
        # Machine-level overlap. The model may use it as timing context but must not rewrite it.
        "audio_overlap_exact": audio.get("voiceover_exact", ""),
        "audio_word_refs": audio.get("word_refs", []),
        "audio_segment_refs": audio.get("segment_refs", []),
        "onscreen_text_sequence": ocr_sequence,
        "observable_scene_sequence": scene_sequence,
        "visual_frame_refs": visual_refs,
        "information_states": info_states,
    }


def validate_annotations(
    annotations: list[dict[str, Any]],
    expected_ids: list[str],
) -> None:
    returned_ids = [str(x.get("shot_id")) for x in annotations]
    if returned_ids != expected_ids:
        raise RuntimeError(
            "Shot annotation IDs/order mismatch.\n"
            f"Expected: {expected_ids}\n"
            f"Returned: {returned_ids}"
        )

    for item in annotations:
        shot_id = str(item["shot_id"])

        primary = item.get("primary_role")
        if primary not in ALLOWED_ROLES:
            raise RuntimeError(f"{shot_id}: invalid primary_role={primary!r}")

        secondary = normalize_role_list(item.get("secondary_roles"))
        unknown = [x for x in secondary if x not in ALLOWED_ROLES]
        if unknown:
            raise RuntimeError(f"{shot_id}: invalid secondary_roles={unknown}")

        relation_text = item.get("audio_to_visual_text")
        relation_scene = item.get("audio_to_visual_scene")
        if relation_text not in ALLOWED_RELATIONS:
            raise RuntimeError(
                f"{shot_id}: invalid audio_to_visual_text={relation_text!r}"
            )
        if relation_scene not in ALLOWED_RELATIONS:
            raise RuntimeError(
                f"{shot_id}: invalid audio_to_visual_scene={relation_scene!r}"
            )

        confidence = item.get("confidence")
        if confidence not in {"high", "medium", "low"}:
            raise RuntimeError(f"{shot_id}: invalid confidence={confidence!r}")

        proof = item.get("proof_assessment")
        if not isinstance(proof, dict):
            raise RuntimeError(f"{shot_id}: proof_assessment must be an object")

        is_proof = bool(proof.get("is_proof"))
        proof_type = proof.get("proof_type")

        role_contains_proof = (
            primary == "proof" or "proof" in secondary
        )

        if role_contains_proof and not is_proof:
            raise RuntimeError(
                f"{shot_id}: role includes proof but proof_assessment.is_proof=false"
            )

        if is_proof:
            if proof_type not in ALLOWED_PROOF_TYPES:
                raise RuntimeError(
                    f"{shot_id}: invalid proof_type={proof_type!r}"
                )
            if not str(proof.get("supports_claim", "")).strip():
                raise RuntimeError(f"{shot_id}: proof requires supports_claim")
            if not str(proof.get("basis", "")).strip():
                raise RuntimeError(f"{shot_id}: proof requires basis")


def segment_relation(
    seg_start: float,
    seg_end: float,
    shot_start: float,
    shot_end: float,
) -> str | None:
    """Return human-readable relation of one narration segment to one Shot."""
    overlap_start = max(seg_start, shot_start)
    overlap_end = min(seg_end, shot_end)

    if overlap_end <= overlap_start:
        return None

    starts_in = shot_start <= seg_start < shot_end
    ends_in = shot_start < seg_end <= shot_end

    if starts_in and ends_in:
        return "完整"
    if starts_in and seg_end > shot_end:
        return "开始"
    if seg_start < shot_start and ends_in:
        return "结束"
    if seg_start < shot_start and seg_end > shot_end:
        return "延续"

    return "重叠"


def build_narration_track(audio_data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for seg in audio_data.get("segments", []):
        out.append(
            {
                "segment_id": str(seg["segment_id"]),
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "duration": round(float(seg["end"]) - float(seg["start"]), 6),
                "text": str(seg.get("source_text", "")),
                "source_text": str(seg.get("source_text", "")),
                "reviewed_text": str(seg.get("source_text", "")),
                "changed": False,
                "word_refs": [str(x) for x in seg.get("word_refs", [])],
                "text_authority": "faster-whisper",
                "timing_authority": "faster-whisper",
                "word_refs_authority": "faster-whisper",
            }
        )
    return out


def validate_and_prepare_narration_track(
    audio_data: dict[str, Any],
    shot_boundaries: dict[str, Any],
    narration_review_path: str | None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """
    Returns: (narration_track, narration_review_source, narration_review_closed)
    """

    segments = list(audio_data.get("segments") or [])
    if not segments:
        raise RuntimeError("No audio segments found in audio_v1.")

    if narration_review_path is None:
        return build_narration_track(audio_data), None, True

    review_path = Path(narration_review_path).expanduser().resolve()
    if not review_path.exists():
        raise FileNotFoundError(review_path)

    review_data = read_json(review_path)
    if str(review_data.get("case_id")) != str(audio_data.get("case_id")):
        raise RuntimeError("Narration Review case_id does not match audio_v1.")

    validation = review_data.get("validation", {})
    if not validation.get("passed"):
        raise RuntimeError("Narration Review validation is not passed.")

    manual_review = review_data.get("manual_review", {})
    if bool(manual_review.get("required")):
        raise RuntimeError("Narration Review requires manual action.")

    reviewed_segments = list(review_data.get("segments") or [])
    if len(reviewed_segments) != len(segments):
        raise RuntimeError("Narration Review segment_count mismatch vs audio_v1.")

    if shot_boundaries.get("validation", {}).get("passed") is not True:
        raise RuntimeError("Shot boundaries validation is not passed.")

    if str(shot_boundaries.get("case_id")) != str(audio_data.get("case_id")):
        raise RuntimeError("Shot boundaries case_id does not match audio_v1.")

    reviewed_by_id = {
        str(item["segment_id"]): item for item in reviewed_segments
    }
    audio_ids = [str(x["segment_id"]) for x in segments]
    review_ids = [str(item["segment_id"]) for item in reviewed_segments]
    if audio_ids != review_ids:
        raise RuntimeError(
            "Narration Review segment_id/order mismatch vs audio_v1."
        )

    out: list[dict[str, Any]] = []
    for seg in segments:
        segment_id = str(seg["segment_id"])
        reviewed = reviewed_by_id.get(segment_id)
        if reviewed is None:
            raise RuntimeError(f"{segment_id}: missing review segment.")

        source_text = str(seg.get("source_text", ""))
        reviewed_text = str(reviewed.get("reviewed_text", ""))

        source_word_refs = [str(x) for x in seg.get("word_refs", [])]
        review_word_refs = [str(x) for x in reviewed.get("word_refs", [])]

        if not float_eq(float(seg["start"]), float(reviewed.get("start", -1.0))):
            raise RuntimeError(
                f"{segment_id}: reviewed start mismatch with audio_v1."
            )
        if not float_eq(float(seg["end"]), float(reviewed.get("end", -1.0))):
            raise RuntimeError(
                f"{segment_id}: reviewed end mismatch with audio_v1."
            )
        if source_word_refs != review_word_refs:
            raise RuntimeError(
                f"{segment_id}: reviewed word_refs mismatch with audio_v1."
            )

        if str(reviewed.get("source_text", "")) != source_text:
            raise RuntimeError(
                f"{segment_id}: review source_text differs from audio_v1 source_text."
            )

        out.append(
            {
                "segment_id": segment_id,
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "duration": round(float(seg["end"]) - float(seg["start"]), 6),
                "text": reviewed_text,
                "source_text": source_text,
                "reviewed_text": reviewed_text,
                "changed": reviewed_text != source_text,
                "word_refs": source_word_refs,
                "text_authority": "narration_review_v1",
                "timing_authority": "faster-whisper",
                "word_refs_authority": "faster-whisper",
            }
        )

    return out, "narration_review_v1", True


def build_narration_links(
    narration_track: list[dict[str, Any]],
    shot_start: float,
    shot_end: float,
) -> list[dict[str, Any]]:
    links = []

    for segment in narration_track:
        relation = segment_relation(
            float(segment["start"]),
            float(segment["end"]),
            shot_start,
            shot_end,
        )
        if relation is None:
            continue

        overlap_start = max(float(segment["start"]), shot_start)
        overlap_end = min(float(segment["end"]), shot_end)

        links.append(
            {
                "segment_id": segment["segment_id"],
                "relation": relation,
                "full_text": segment["text"],
                "source_full_text": segment["source_text"],
                "segment_start": segment["start"],
                "segment_end": segment["end"],
                "overlap_start": round(overlap_start, 6),
                "overlap_end": round(overlap_end, 6),
                "overlap_duration": round(overlap_end - overlap_start, 6),
            }
        )

    return links


def flatten_word_refs_from_segments(
    segments: list[dict[str, Any]],
) -> list[str]:
    refs: list[str] = []
    for segment in segments:
        refs.extend(str(x) for x in segment.get("word_refs", []))
    return refs


def narration_link_label(links: list[dict[str, Any]]) -> str:
    if not links:
        return "无旁白"

    parts = []
    for link in links:
        parts.append(
            f"{link['segment_id']} {link['relation']}"
        )
    return " → ".join(parts)


def validate_video_understanding(
    video_understanding: dict[str, Any],
    interpretation_by_shot_id: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(video_understanding, dict):
        raise RuntimeError("video_understanding must be an object.")

    required = {
        "content_goal_candidate",
        "hook_candidate",
        "audio_role",
        "visual_text_role",
        "visual_scene_role",
        "audio_visual_strategy",
        "structure_sequence",
        "claims",
        "verified_proofs",
        "uncertainties",
    }

    missing = required - set(video_understanding.keys())
    if missing:
        raise RuntimeError(
            "video_understanding missing fields: "
            + ", ".join(sorted(missing))
        )

    hook_candidate = video_understanding.get("hook_candidate")
    if not isinstance(hook_candidate, dict):
        raise RuntimeError("video_understanding.hook_candidate must be an object.")
    for key in ("audio", "visual_text", "visual_scene"):
        if key not in hook_candidate:
            raise RuntimeError(
                f"video_understanding.hook_candidate.{key} is required."
            )

    structure_sequence = video_understanding.get("structure_sequence")
    if not isinstance(structure_sequence, list):
        raise RuntimeError(
            "video_understanding.structure_sequence must be an array."
        )

    valid_stages = {
        "hook",
        "setup",
        "development",
        "demonstration",
        "transition",
        "payoff",
        "CTA",
        "other",
    }

    proof_shot_ids = {
        shot_id
        for shot_id, item in interpretation_by_shot_id.items()
        if bool(item.get("proof_assessment", {}).get("is_proof"))
    }
    for item in structure_sequence:
        stage = item.get("stage")
        if stage not in valid_stages:
            raise RuntimeError(
                f"structure_sequence item has invalid stage {stage!r}."
            )
        shot_refs = item.get("shot_refs")
        if not isinstance(shot_refs, list):
            raise RuntimeError("structure_sequence shot_refs must be a list.")

    for proof in video_understanding.get("verified_proofs", []):
        if not isinstance(proof, dict):
            continue
        refs = [str(x) for x in proof.get("shot_refs", [])]
        if not all(ref in proof_shot_ids for ref in refs):
            raise RuntimeError(
                "video_understanding.verified_proofs references shot "
                "not validated as proof."
            )


def call_model_json(
    model: str,
    prompt: str,
    max_tokens: int = 14000,
) -> tuple[dict[str, Any], float]:
    client = get_client()

    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "disabled"}},
    )
    elapsed = time.perf_counter() - started

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("DeepSeek returned empty content.")
    return json.loads(content), elapsed


def load_or_generate_interpretation(
    args: argparse.Namespace,
    shot_inputs: list[dict[str, Any]],
    narration_track: list[dict[str, Any]],
    expected_ids: list[str],
    cache_root: Path,
    cache_narration_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], float, str]:
    if args.reuse_existing:
        reuse_path = Path(args.reuse_existing).expanduser().resolve()
        if not reuse_path.exists():
            raise FileNotFoundError(reuse_path)
        previous = read_json(reuse_path)

        annotations: list[dict[str, Any]] = []
        for shot in previous.get("shots", []):
            interpretation = shot.get("interpretation")
            if interpretation:
                annotations.append(interpretation)

        validate_annotations(annotations, expected_ids)
        video_understanding = previous.get("video_understanding", {})
        validate_video_understanding(video_understanding, {x["shot_id"]: x for x in annotations})
        return annotations, video_understanding, 0.0, f"reused:{reuse_path}"

    chunk_size = max(1, int(args.interpretation_chunk_size))
    total_chunks = (len(shot_inputs) + chunk_size - 1) // chunk_size

    all_annotations: list[dict[str, Any]] = []
    all_elapsed = 0.0

    transcript_preview = [
        {
            "segment_id": str(x["segment_id"]),
            "text": str(x["text"]),
        }
        for x in narration_track
    ]

    chunk_cache_count = 0
    chunk_run_count = 0

    for chunk_index in range(total_chunks):
        start = chunk_index * chunk_size
        chunk_shots = shot_inputs[start : start + chunk_size]
        chunk_ids = [str(x["shot_id"]) for x in chunk_shots]

        prior_context = None
        if all_annotations:
            prior = all_annotations[-1]
            prior_context = {
                "shot_id": prior.get("shot_id"),
                "primary_role": prior.get("primary_role"),
                "secondary_roles": prior.get("secondary_roles", []),
                "narrative_function": prior.get("narrative_function"),
            }

        chunk_input = {
            "chunk_shots": chunk_shots,
            "transcript_preview": transcript_preview,
            "prior_context": prior_context,
            "chunk_index": chunk_index + 1,
            "total_chunks": total_chunks,
            "narration_review_source": cache_narration_mode,
        }

        profile = {
            "model": args.model,
            "prompt_version": INTERPRETATION_PROMPT_VERSION,
            "interpretation_chunk_size": chunk_size,
            "input_content_hash": stable_hash(chunk_input),
            "narration_source_mode": cache_narration_mode,
        }

        cache_path = cache_root / f"chunk_{chunk_index + 1:03d}.json"

        cached = read_json(cache_path) if cache_path.exists() else None
        if cached is not None and dict(cached.get("cache", {})) == profile:
            annotations = cached.get("model_output", {}).get("shot_annotations")
            if not isinstance(annotations, list):
                raise RuntimeError(
                    f"Cached chunk {chunk_index + 1} invalid."
                )
            returned_ids = [str(x.get("shot_id")) for x in annotations]
            if returned_ids != chunk_ids:
                raise RuntimeError(
                    f"Cached chunk {chunk_index + 1} shot IDs mismatch."
                )
            chunk_cache_count += 1
            all_elapsed += float(cached.get("model_elapsed_seconds") or 0.0)
        else:
            chunk_run_count += 1
            chunk_prompt = (
                f"""
你正在生成“逆向分镜脚本 V1.1”。  
这是第 {chunk_index + 1} / {total_chunks} 个 Chunk。  
你只需要返回本 Chunk 的 Shot 解释，不返回全局变量，不输出额外字段。

输入已经包含：
- 程序约束后的真实 Shot 边界；
- 按 word midpoint 恰好分配一次的旁白重叠片段；
- Qwen3-VL 从真实候选帧中提取的 OCR 与可观察场景。

你只负责解释 Shot 的内容作用。
你不能修改任何时间、旁白、OCR、source frame，也不能创建或删除 Shot。

【角色词典】

primary_role / secondary_roles 只能使用：

hook
= 视频最早承担抓取注意力的镜头作用。

context
= 提供地点、环境、业务背景、人物所处情境。

action
= 主要价值是展示动作、过程、行为。

persona
= 主要价值是建立人物存在感、生活感、工作状态或人格表达。
不得据此确认人物真实身份或职业。

product
= 明确展示产品、食物、服务对象或可识别业务对象。
只有画面直接支持时使用。

claim
= 提出观点、判断、承诺、主张。

explanation
= 对前述观点或信息进行解释、展开。

emotion
= 主要承担情绪氛围或情绪表达。

proof
= 只有真正可验证材料才能使用。
例如：数据、订单、后台截图、客户评价、前后对比、证书、明确结果、可核验案例结果。
“人物在干活”“顾客在场”“人物做饭”“有人排队/吃饭”本身都不是 proof。

transition
= 镜头主要用于过渡、连接，而非传递独立内容。

payoff
= 对前文进行收束、落点、回扣或结论强化。

CTA
= 明确要求观众进行咨询、下单、到店、关注、私信等行动。

other
= 以上均不适用。

【严格边界】

1. 处理食材、搬运、行走、操作设备、与顾客互动等，一般属于 action/context/persona，不自动属于 proof。
2. 人多、有人用餐、有人互动，不能证明商业成功或生意好。
3. 不得根据视觉外表确认人物性别、身份、职业、老板身份、店铺归属。
4. Shot 可以在一句旁白中间切换，audio_overlap_exact 可能是碎片；这是正常时间事实，不得自行合并或改写。
5. 完整旁白只用于理解上下文，不能用来替换每个 Shot 的 exact overlap。
6. 不生成 Pattern。
7. 不评价“爆款”“有效”“高转化”，除非以后有真实数据支持。

【音画关系】

audio_to_visual_text / audio_to_visual_scene 只能使用：
repeat / reinforce / supplement / independent / conflict / unknown

【Proof Assessment】

每个 Shot 都必须返回：
proof_assessment.is_proof = true/false

只有 true 时：
proof_type 必须是以下之一：
data
customer_review
before_after
order
dashboard
certificate
physical_result
documented_case_result
other_verifiable

并说明 supports_claim 与 basis。

【输入完整旁白，仅作上下文】

{json.dumps(transcript_preview, ensure_ascii=False)}

【本 Chunk Shot 输入】

{json.dumps(chunk_shots, ensure_ascii=False)}

"""
                + (
                    ""
                    if not prior_context
                    else f"""
前一个 Chunk 最后 Shot 的 compact context（仅用于连贯性）：
{json.dumps(prior_context, ensure_ascii=False)}
"""
                )
                + """
只输出 JSON：

{
  "shot_annotations": [
    {
      "shot_id": "S001",
      "primary_role": "hook",
      "secondary_roles": ["context"],
      "narrative_function": "一句简洁说明该 Shot 在原视频中的作用，不新增事实。",
      "audio_to_visual_text": "repeat",
      "audio_to_visual_scene": "supplement",
      "proof_assessment": {
        "is_proof": false,
        "proof_type": null,
        "supports_claim": "",
        "basis": ""
      },
      "confidence": "high|medium|low",
      "uncertainties": []
    }
  ]
}
"""
            )

            model_output, model_elapsed = call_model_json(
                args.model,
                chunk_prompt,
                max_tokens=14000,
            )
            all_elapsed += model_elapsed

            annotations = model_output.get("shot_annotations")
            if not isinstance(annotations, list):
                raise RuntimeError(
                    f"Chunk {chunk_index + 1} missing shot_annotations array."
                )
            validate_annotations(annotations, chunk_ids)

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(
                    {
                        "cache": profile,
                        "model_elapsed_seconds": round(model_elapsed, 6),
                        "model_output": {"shot_annotations": annotations},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        all_annotations.extend(annotations)

    # Reuse existing shot ids/order exactly once.
    returned_ids = [str(x["shot_id"]) for x in all_annotations]
    if returned_ids != expected_ids:
        raise RuntimeError(
            "Shot interpretation IDs/order mismatch across all chunks.\n"
            f"Expected: {expected_ids}\nReturned: {returned_ids}"
        )

    shot_input_map = {
        str(item["shot_id"]): item for item in shot_inputs
    }
    compact_shots: list[dict[str, Any]] = []
    for item in all_annotations:
        shot_id = str(item["shot_id"])
        shot_input = shot_input_map[shot_id]
        compact_shots.append(
            {
                "shot_id": shot_id,
                "start": shot_input["start"],
                "end": shot_input["end"],
                "primary_role": item.get("primary_role"),
                "secondary_roles": item.get("secondary_roles", []),
                "narrative_function": item.get("narrative_function"),
                "proof_assessment": item.get("proof_assessment", {}),
                "onscreen_text_sequence": shot_input.get(
                    "onscreen_text_sequence", []
                ),
                "observable_scene_sequence": shot_input.get(
                    "observable_scene_sequence", []
                ),
            }
        )

    global_cache_profile = {
        "model": args.model,
        "prompt_version": GLOBAL_UNDERSTANDING_PROMPT_VERSION,
        "input_content_hash": stable_hash(
            {
                "compact_shots": compact_shots,
                "transcript_preview": transcript_preview,
            }
        ),
        "narration_source_mode": cache_narration_mode,
    }

    global_cache_path = cache_root / "global_understanding.json"
    global_cached = (
        read_json(global_cache_path)
        if global_cache_path.exists()
        else None
    )
    if global_cached is not None and (
        dict(global_cached.get("cache", {})) == global_cache_profile
    ):
        video_understanding = global_cached.get("model_output")
        if not isinstance(video_understanding, dict):
            raise RuntimeError("Cached global understanding invalid.")
        validate_video_understanding(
            video_understanding,
            {x["shot_id"]: x for x in all_annotations},
        )
        all_elapsed += float(global_cached.get("model_elapsed_seconds") or 0.0)
        global_source = f"cached:{global_cache_path}"
    else:
        global_prompt = f"""
你正在生成“逆向分镜脚本 V1.1 的全局理解”。

输入是紧凑 shot 解释与完整旁白文本（仅用于语义理解）：

完整旁白（按 Narration Track 顺序）：
{json.dumps(transcript_preview, ensure_ascii=False)}

Shot 解释汇总：
{json.dumps(compact_shots, ensure_ascii=False)}

只输出 JSON：

{
  "content_goal_candidate": "",
  "hook_candidate": {
    "audio": "",
    "visual_text": "",
    "visual_scene": ""
  },
  "audio_role": "",
  "visual_text_role": "",
  "visual_scene_role": "",
  "audio_visual_strategy": "",
  "structure_sequence": [
    {
      "shot_refs": ["S001", "S002"],
      "stage": "hook|setup|development|demonstration|transition|payoff|CTA|other",
      "description": ""
    }
  ],
  "claims": [],
  "verified_proofs": [],
  "uncertainties": []
}

要求：
- 不生成 Pattern；
- 不修改时间、OCR、word 证据；
- output 必须 JSON。
"""

        video_understanding, global_elapsed = call_model_json(
            args.model,
            global_prompt,
            max_tokens=12000,
        )
        all_elapsed += global_elapsed
        validate_video_understanding(
            video_understanding,
            {x["shot_id"]: x for x in all_annotations},
        )
        global_source = f"generated:{args.model}"

        global_cache_path.parent.mkdir(parents=True, exist_ok=True)
        global_cache_path.write_text(
            json.dumps(
                {
                    "cache": global_cache_profile,
                    "model_elapsed_seconds": round(global_elapsed, 6),
                    "model_output": video_understanding,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    interpretation_source = (
        "chunks="
        + (
            "all_cached"
            if chunk_cache_count == total_chunks and chunk_run_count == 0
            else "all_generated"
            if chunk_run_count == total_chunks and chunk_cache_count == 0
            else f"mixed:{chunk_cache_count}cached/{chunk_run_count}generated"
        )
        + f";global={global_source}"
    )

    return all_annotations, video_understanding, all_elapsed, interpretation_source


def main() -> None:
    total_started = time.perf_counter()

    parser = argparse.ArgumentParser(
        description=(
            "Generate Reverse Storyboard V1.1. "
            "Narration Track and Visual Shot Track are separate; "
            "machine exact audio overlap is retained but not used as human-facing narration text."
        )
    )
    parser.add_argument("--shot-boundaries", required=True)
    parser.add_argument("--audio-v1", required=True)
    parser.add_argument(
        "--narration-review",
        default=None,
        help=(
            "Optional Narration Review artifact path. "
            "If provided, narration track will use reviewed text."
        ),
    )
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument(
        "--interpretation-chunk-size",
        type=int,
        default=10,
        help="Chunk size for shot interpretation calls. Default 10.",
    )
    parser.add_argument(
        "--reuse-existing",
        default=None,
        help=(
            "Reuse interpretations/video_understanding from an existing "
            "reverse_storyboard_v1.json without another model call."
        ),
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/storyboards/<case_id>/v1",
    )
    args = parser.parse_args()

    shot_path = Path(args.shot_boundaries).expanduser().resolve()
    audio_path = Path(args.audio_v1).expanduser().resolve()

    for path in (shot_path, audio_path):
        if not path.exists():
            raise FileNotFoundError(path)

    shot_data = read_json(shot_path)
    audio_data = read_json(audio_path)

    shot_validation = shot_data.get("validation", {})
    if shot_validation.get("passed") is not True:
        raise RuntimeError("Shot boundaries validation is not passed.")
    if shot_validation.get("manual_review", {}).get("required"):
        raise RuntimeError("Shot boundaries manual review is required.")

    audio_validation = audio_data.get("validation", {})
    if audio_validation.get("passed") is not True:
        raise RuntimeError("Audio V1 validation is not passed.")

    case_id = str(shot_data["case_id"])
    if str(audio_data.get("case_id")) != case_id:
        raise RuntimeError("Audio V1 case_id does not match shot boundaries.")

    source_shots = list(shot_data.get("shots") or [])
    if not source_shots:
        raise RuntimeError("No deterministic shots found.")

    project_root = Path(__file__).resolve().parents[1]
    output_dir = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "storyboards" / case_id / "v1"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_root = output_dir / "interpretation_cache"

    narration_track, narration_review_source, narration_review_closed = validate_and_prepare_narration_track(
        audio_data,
        shot_data,
        args.narration_review,
    )

    shot_inputs = [build_shot_input(x) for x in source_shots]
    expected_ids = [x["shot_id"] for x in shot_inputs]

    annotations, video_understanding, model_elapsed, interpretation_source = (
        load_or_generate_interpretation(
            args,
            shot_inputs,
            narration_track,
            expected_ids,
            cache_root,
            narration_review_source or "faster-whisper",
        )
    )

    annotation_by_id = {x["shot_id"]: x for x in annotations}
    audio_segments = list(audio_data.get("segments") or [])
    if len(audio_segments) != len(narration_track):
        raise RuntimeError("Narration track segment count does not match Audio V1.")

    audio_by_id = {str(seg["segment_id"]): seg for seg in audio_segments}
    for track_segment in narration_track:
        segment_id = str(track_segment["segment_id"])
        source_segment = audio_by_id.get(segment_id)
        if source_segment is None:
            raise RuntimeError(f"{segment_id}: narration segment missing in audio_v1.")
        source_word_refs = [str(x) for x in source_segment.get("word_refs", [])]
        if [str(x) for x in track_segment.get("word_refs", [])] != source_word_refs:
            raise RuntimeError(
                f"{segment_id}: narration word_refs do not match audio_v1."
            )
        if not float_eq(float(source_segment["start"]), float(track_segment["start"])):
            raise RuntimeError(
                f"{segment_id}: narration start timing changed from audio_v1."
            )
        if not float_eq(float(source_segment["end"]), float(track_segment["end"])):
            raise RuntimeError(
                f"{segment_id}: narration end timing changed from audio_v1."
            )

    shot_inputs_by_id = {str(x["shot_id"]): x for x in shot_inputs}

    # Validate every narration segment is represented by at least one Shot link.
    linked_segment_ids = set()
    final_shots: list[dict[str, Any]] = []
    all_shot_intervals: list[tuple[float, float, str]] = []
    for source_shot in source_shots:
        all_shot_intervals.append(
            (
                float(source_shot["start"]),
                float(source_shot["end"]),
                str(source_shot["shot_id"]),
            )
        )

    for source_shot in source_shots:
        shot_id = source_shot["shot_id"]
        shot_id = str(shot_id)
        shot_input = shot_inputs_by_id[shot_id]

        start = float(source_shot["start"])
        end = float(source_shot["end"])
        narration_links = build_narration_links(
            narration_track,
            start,
            end,
        )
        for link in narration_links:
            linked_segment_ids.add(link["segment_id"])

        if shot_id not in annotation_by_id:
            raise RuntimeError(f"Missing interpretation for shot {shot_id}.")

        final_shots.append(
            {
                "shot_id": shot_id,
                "start": source_shot["start"],
                "end": source_shot["end"],
                "duration": source_shot["duration"],
                "boundary": source_shot.get("boundary", {}),
                "evidence": {
                    "audio_overlap_exact": source_shot.get(
                        "audio_projection", {}
                    ).get("voiceover_exact", ""),
                    "audio_word_refs": source_shot.get(
                        "audio_projection", {}
                    ).get("word_refs", []),
                    "audio_segment_refs": source_shot.get(
                        "audio_projection", {}
                    ).get("segment_refs", []),
                    "narration_links": narration_links,
                    "narration_display": narration_link_label(
                        narration_links
                    ),
                    "onscreen_text_sequence": shot_input["onscreen_text_sequence"],
                    "observable_scene_sequence": shot_input[
                        "observable_scene_sequence"
                    ],
                    "visual_frame_refs": shot_input["visual_frame_refs"],
                    "information_states": shot_input["information_states"],
                },
                "interpretation": annotation_by_id[shot_id],
            }
        )

    proof_shot_ids = {
        str(x["shot_id"])
        for x in annotations
        if bool(x.get("proof_assessment", {}).get("is_proof"))
    }

    verified_proofs = video_understanding.get("verified_proofs", [])
    for proof in verified_proofs:
        refs = proof.get("shot_refs", []) if isinstance(proof, dict) else []
        if not refs or any(str(x) not in proof_shot_ids for x in refs):
            raise RuntimeError(
                "video_understanding.verified_proofs references a shot "
                "not validated as proof."
            )

    final_shot_ids = [str(x["shot_id"]) for x in final_shots]
    if final_shot_ids != expected_ids:
        raise RuntimeError(
            "Final shots differ from input Shot IDs/order.\n"
            f"Expected: {expected_ids}\n"
            f"Returned: {final_shot_ids}"
        )

    missing_narration_links = []
    for segment in narration_track:
        seg_id = segment["segment_id"]
        seg_start = float(segment["start"])
        seg_end = float(segment["end"])
        has_coverage = any(
            seg_end > shot_start and seg_start < shot_end
            for shot_start, shot_end, _ in all_shot_intervals
        )
        if has_coverage and seg_id not in linked_segment_ids:
            missing_narration_links.append(seg_id)

    if missing_narration_links:
        raise RuntimeError(
            "Narration segments missing from Shot relationship view: "
            + ", ".join(missing_narration_links)
        )

    total_elapsed = time.perf_counter() - total_started

    shot_manual_review_closed = not bool(
        shot_validation.get("manual_review", {}).get("required")
    )
    audio_manual_review_closed = not bool(
        audio_validation.get("manual_review", {}).get("required")
    )
    manual_review_closed = (
        shot_manual_review_closed
        and audio_manual_review_closed
        and bool(narration_review_closed)
    )

    result = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "source_artifacts": {
            "shot_boundaries": str(shot_path),
            "audio_v1": str(audio_path),
            "narration_review_v1": (
                str(Path(args.narration_review).expanduser().resolve())
                if args.narration_review
                else None
            ),
        },
        "storyboard_type": "reverse",
        "narration_track": narration_track,
        "shots": final_shots,
        "video_understanding": video_understanding,
        "authority": {
            "narration_text": narration_review_source or "faster-whisper",
            "narration_timing": "audio_word_timeline_v1 / faster-whisper",
            "audio_overlap_exact": "audio_word_timeline_v1",
            "visual_evidence": "qwen3-vl_visual_v1",
            "time_and_shot_order": "shot_boundaries_v1_1",
            "roles_and_video_understanding": "deepseek-v4-flash",
            "pattern_mining": "not_performed",
        },
        "design_decision": {
            "narration_and_shots_are_separate_tracks": True,
            "shot_to_narration_cardinality": "many_to_many",
            "human_facing_storyboard_uses_narration_links": True,
            "audio_overlap_exact_is_machine_sync_field": True,
            "do_not_treat_audio_overlap_exact_as_script_copy": True,
        },
        "timing": {
            "deepseek_storyboard_seconds": round(model_elapsed, 6),
            "total_elapsed_seconds": round(total_elapsed, 6),
            "interpretation_source": interpretation_source,
            "interpretation_chunk_size": int(args.interpretation_chunk_size),
        },
        "validation": {
            "passed": True,
            "shot_count": len(final_shots),
            "narration_segment_count": len(narration_track),
            "all_input_shots_preserved_exactly_once": True,
            "all_narration_segments_linked_to_at_least_one_shot": True,
            "time_generated_by_model": False,
            "audio_generated_by_model": False,
            "ocr_generated_by_model": False,
            "pattern_generated_in_this_stage": False,
            "proof_role_strictly_validated": True,
            "audio_validation_passed": audio_validation.get("passed"),
            "shot_validation_passed": shot_validation.get("passed"),
            "manual_review_closed": manual_review_closed,
            "narration_review_closed": bool(narration_review_closed),
            "pattern_not_generated": True,
        },
    }

    json_path = output_dir / "reverse_storyboard_v1.json"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    raw_output = {
        "shot_annotations": annotations,
        "video_understanding": video_understanding,
    }
    if not args.reuse_existing:
        raw_path = output_dir / "reverse_storyboard_v1_model_raw.json"
        raw_path.write_text(
            json.dumps(raw_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    md = [
        "# 逆向分镜脚本 V1.1",
        "",
        f"- Case ID：`{case_id}`",
        f"- Shot 数：`{len(final_shots)}`",
        f"- 完整旁白段：`{len(narration_track)}`",
        f"- Interpretation：`{interpretation_source}`",
        "",
        "> **重要：旁白轨与视觉分镜轨是两条独立时间轨。**",
        "> 一个完整旁白段可以跨多个 Shot，一个 Shot 也可能跨多个旁白段。",
        "> JSON 中的 `audio_overlap_exact` 只用于机器同步，不作为人类可读旁白脚本。",
        "",
        "## 完整旁白轨",
        "",
        "| 旁白段 | 时间 | 时长 | 文本（可读） |",
        "|---|---|---:|---|",
    ]

    for seg in narration_track:
        text = str(seg["text"]).replace("|", "｜")
        md.append(
            f"| {seg['segment_id']} | "
            f"{seg['start']:.3f}–{seg['end']:.3f}s | "
            f"{seg['duration']:.3f}s | "
            f"{text} |"
        )

    md += [
        "",
        "## 视觉分镜轨",
        "",
        "| Shot | 时间 | 时长 | 旁白关联 | 画面文字 | 可观察画面 | 主作用 | 次作用 | Proof |",
        "|---|---|---:|---|---|---|---|---|---|",
    ]

    for shot in final_shots:
        ev = shot["evidence"]
        it = shot["interpretation"]

        narration_display = str(
            ev["narration_display"]
        ).replace("|", "｜")

        ocr = " / ".join(
            ev["onscreen_text_sequence"]
        ).replace("|", "｜")

        scenes = " / ".join(
            ev["observable_scene_sequence"]
        ).replace("|", "｜")

        secondary = ", ".join(
            it.get("secondary_roles", [])
        )

        proof = (
            "YES"
            if it.get(
                "proof_assessment", {}
            ).get("is_proof")
            else "NO"
        )

        md.append(
            f"| {shot['shot_id']} | "
            f"{shot['start']:.3f}–{shot['end']:.3f}s | "
            f"{shot['duration']:.3f}s | "
            f"{narration_display} | "
            f"{ocr} | {scenes} | "
            f"{it['primary_role']} | "
            f"{secondary} | {proof} |"
        )

    md += [
        "",
        "## 视频理解",
        "",
        f"- **内容目标候选**：{video_understanding.get('content_goal_candidate', '')}",
        f"- **Audio 作用**：{video_understanding.get('audio_role', '')}",
        f"- **画面文字作用**：{video_understanding.get('visual_text_role', '')}",
        f"- **视觉场景作用**：{video_understanding.get('visual_scene_role', '')}",
        f"- **音画策略**：{video_understanding.get('audio_visual_strategy', '')}",
        "",
        "### 结构序列",
        "",
    ]

    for item in video_understanding.get(
        "structure_sequence", []
    ):
        md.append(
            f"- **{item.get('stage', '')}** "
            f"({', '.join(item.get('shot_refs', []))})："
            f"{item.get('description', '')}"
        )

    md += [
        "",
        "### Claims",
        "",
    ]

    for item in video_understanding.get("claims", []):
        md.append(f"- {item}")

    md += [
        "",
        "### Verified Proofs",
        "",
    ]

    proofs = video_understanding.get(
        "verified_proofs", []
    )
    if proofs:
        for item in proofs:
            md.append(
                f"- {item.get('description', item)}"
                if isinstance(item, dict)
                else f"- {item}"
            )
    else:
        md.append("- 无已验证 Proof。")

    md += [
        "",
        "## 机器同步说明",
        "",
        "- `audio_overlap_exact` 仍保留在 JSON 中，用于字幕、剪辑、TTS、BGM ducking 等机器级同步。",
        "- 人类主表通过 `A001 开始 / A001 延续 / A001 结束 / A001 完整` 等方式表达旁白与 Shot 的关系。",
    ]

    md_path = output_dir / "reverse_storyboard_v1.md"
    md_path.write_text(
        "\n".join(md),
        encoding="utf-8",
    )

    metric = {
        "run_id": (
            f"storyboard-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:6]}"
        ),
        "stage": "reverse_storyboard_v1_1",
        "case_id": case_id,
        "model": args.model,
        "interpretation_source": interpretation_source,
        "interpretation_chunk_size": int(args.interpretation_chunk_size),
        "source_video_duration_seconds": shot_data.get(
            "duration_seconds"
        ),
        "shot_count": len(final_shots),
        "narration_segment_count": len(narration_track),
        "model_elapsed_seconds": round(model_elapsed, 6),
        "total_elapsed_seconds": round(total_elapsed, 6),
        "created_at": now_iso(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "gpu": gpu_name(),
        },
    }

    metrics_log = (
        project_root
        / "data"
        / "metrics"
        / "storyboard_runs.jsonl"
    )
    append_jsonl(metrics_log, metric)

    print()
    print("REVERSE STORYBOARD V1.1 PASS")
    print(f"Case ID: {case_id}")
    print(f"Shots preserved: {len(final_shots)}")
    print(f"Narration segments: {len(narration_track)}")
    print("Narration / Shot tracks separated: YES")
    print("Machine audio overlap retained: YES")
    print(f"Interpretation source: {interpretation_source}")
    print(f"DeepSeek storyboard: {model_elapsed:.2f}s")
    print(f"Total elapsed: {total_elapsed:.2f}s")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print(f"Metrics: {metrics_log}")


if __name__ == "__main__":
    main()
