import argparse
import json
from pathlib import Path

from ollama import chat


def format_time(seconds):
    if seconds is None:
        return "unknown"

    seconds = float(seconds)
    minutes = int(seconds // 60)
    secs = seconds % 60

    return f"{minutes:02d}:{secs:06.3f}"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Merge audio and visual evidence "
            "into a unified short-video timeline."
        )
    )

    parser.add_argument(
        "--audio",
        required=True,
        help="Path to transcript_segments.json",
    )

    parser.add_argument(
        "--visual",
        required=True,
        help="Path to visual_timeline_raw.txt",
    )

    parser.add_argument(
        "--visual-frames",
        required=True,
        help="Path to visual_timeline_frames.json",
    )

    parser.add_argument(
        "--case-id",
        required=True,
    )

    parser.add_argument(
        "--model",
        default="qwen3-vl:4b-instruct",
    )

    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    visual_path = Path(args.visual).resolve()
    visual_frames_path = Path(
        args.visual_frames
    ).resolve()

    for path in (
        audio_path,
        visual_path,
        visual_frames_path,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    # -----------------------------------------
    # Load Audio Evidence
    # -----------------------------------------

    audio_data = json.loads(
        audio_path.read_text(
            encoding="utf-8"
        )
    )

    raw_segments = audio_data.get(
        "segments",
        []
    )

    audio_segments = []

    for segment in raw_segments:
        audio_segments.append(
            {
                "start": segment.get("start"),
                "end": segment.get("end"),
                "start_display": format_time(
                    segment.get("start")
                ),
                "end_display": format_time(
                    segment.get("end")
                ),
                "text": segment.get(
                    "text",
                    "",
                ).strip(),
            }
        )

    # -----------------------------------------
    # Load Visual Evidence
    # -----------------------------------------

    visual_raw = visual_path.read_text(
        encoding="utf-8"
    )

    visual_frames = json.loads(
        visual_frames_path.read_text(
            encoding="utf-8"
        )
    )

    # -----------------------------------------
    # Build input package
    # -----------------------------------------

    evidence_package = {
        "case_id": args.case_id,
        "audio_evidence": {
            "engine": "faster-whisper",
            "segments": audio_segments,
        },
        "visual_evidence": {
            "frame_mapping": (
                visual_frames.get(
                    "frames",
                    []
                )
            ),
            "analysis": visual_raw,
        },
    }

    evidence_json = json.dumps(
        evidence_package,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
你正在进行短视频案例的“证据融合”。

你的任务不是重新分析视频，
也不是创作文案。

你只允许使用下面提供的两个来源：

AUDIO_EVIDENCE：
来自 faster-whisper 的音频转写与时间范围。

VISUAL_EVIDENCE：
来自 Qwen3-VL 对按时间排序视觉帧的分析。

========================
核心规则
========================

1. 原始证据不可修改。

2. 不得为了让故事更连贯而补充不存在的信息。

3. 音频证据与视觉证据发生冲突时：
   不允许自行选择其中一方。
   必须记录为 conflict 或 uncertainty。

4. VISUAL_EVIDENCE 是在没有获得音频输入的情况下生成的。

因此类似：
“没有旁白”
“所有信息都来自画面”
这样的判断，
如果没有视觉证据能够直接证明，
不得作为事实继续传播。

5. 人物身份、职业、创业结果、商业成功、
店铺归属、因果关系等，
除非证据直接支持，否则不得确认。

6. 时间对齐必须优先依据时间戳。

7. 对 Audio 与 Visual 的关系，
只能使用以下类型：

repeat
= 音频与画面文字基本表达相同内容

reinforce
= 二者不完全相同，但共同强化同一信息

supplement
= 一方提供另一方没有的新信息

independent
= 同时存在，但承担不同的信息作用

conflict
= 两个证据源明显冲突

unknown
= 无法确认关系

8. “画面展示某个经营动作”
不自动意味着：
创业成功、经营结果、产品优秀或客户认可。

========================
输入证据
========================

{evidence_json}

========================
输出要求
========================

只输出 JSON。

结构必须严格如下：

{{
  "case_id": "{args.case_id}",

  "unified_timeline": [
    {{
      "start": 0.0,
      "end": 2.0,

      "audio": {{
        "text": "",
        "source": "audio_evidence"
      }},

      "visual": {{
        "ocr": "",
        "observable_scene": "",
        "source_frames": []
      }},

      "audio_visual_relation": "repeat",

      "new_information": [
        ""
      ],

      "uncertainties": [
        ""
      ]
    }}
  ],

  "information_architecture": {{
    "audio_role": "",
    "visual_text_role": "",
    "visual_scene_role": "",
    "combined_structure": [
      ""
    ]
  }},

  "hook_candidates": {{
    "audio": "",
    "visual_text": "",
    "visual_scene": ""
  }},

  "evidence_present": [
  ],

  "claims_without_evidence": [
  ],

  "conflicts": [
  ],

  "missing_or_unsampled_information": [
  ],

  "overall_uncertainties": [
  ],

  "fusion_quality": {{
    "audio_coverage": "high|medium|low",
    "visual_coverage": "high|medium|low",
    "timeline_alignment": "high|medium|low",
    "notes": ""
  }}
}}

注意：

unified_timeline 不需要机械地为每一帧生成一行。

应该按“信息状态变化”建立时间段。

如果连续多个画面承担相同信息，
应合并成一个时间段。

如果 Visual Timeline 明显漏掉了
Audio 中已经出现的重要字幕对应状态，
请记录到：

missing_or_unsampled_information

不要自行虚构漏掉的画面文字。
"""

    print(
        f"Case: {args.case_id}"
    )
    print(
        f"Audio segments: "
        f"{len(audio_segments)}"
    )
    print(
        f"Visual frames: "
        f"{len(visual_frames.get('frames', []))}"
    )
    print()
    print("Merging evidence...")

    response = chat(
        model=args.model,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        format="json",
        options={
            "temperature": 0,
            "num_ctx": 16384,
        },
        keep_alive=0,
    )

    raw_result = (
        response.message.content
    )

    try:
        result = json.loads(
            raw_result
        )
    except json.JSONDecodeError:
        raise RuntimeError(
            "Model did not return valid JSON:\n"
            + raw_result
        )

    # -----------------------------------------
    # Output
    # -----------------------------------------

    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    output_dir = (
        project_root
        / "data"
        / "unified"
        / args.case_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_output = (
        output_dir
        / "unified_video_evidence.json"
    )

    raw_output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    source_manifest = {
        "case_id": args.case_id,
        "inputs": {
            "audio": str(audio_path),
            "visual": str(visual_path),
            "visual_frames": str(
                visual_frames_path
            ),
        },
        "fusion": {
            "model": args.model,
            "temperature": 0,
            "num_ctx": 16384,
        },
    }

    (
        output_dir
        / "fusion_manifest.json"
    ).write_text(
        json.dumps(
            source_manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )
    print("=" * 70)
    print()
    print(
        f"Saved: {raw_output}"
    )


if __name__ == "__main__":
    main()