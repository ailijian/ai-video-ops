# AI 短视频案例逆向工程 MVP｜团队演示操作手册 V0.1

> **Status：Historical / Non-canonical**
> **Warning：Contains obsolete commands. Do not use for current production.**
> **Current Operations：** [docs/operations/RUNBOOK.md](../docs/operations/RUNBOOK.md)
> 本文仅作为历史演示与调查记录保留，不是 Current Authority，也不是当前 RUNBOOK。

> **用途**：团队内部现场演示  
> **目标**：从一条抖音案例开始，依次完成下载、旁白识别、视觉抽取、多帧视觉理解、确定性音画对齐、语义融合，并最终输出一份可读的逆向分镜脚本。  
> **当前原则**：先用脚本把真实业务流程跑通，再决定哪些环节交给 Codex 产品化/自动化。

---

## 一、这次演示要证明什么

演示不是为了证明“我们会下载视频”，而是为了证明：

**一个公开短视频案例，可以被自动转化为公司可继续复用的结构化内容资产。**

完整链路：

```text
抖音分享链接
    ↓
douyin-downloader
    ↓
MP4 + Music + Cover + Metadata
    ↓
┌──────────────────────┬──────────────────────┐
│                      │                      │
│ faster-whisper       │ PySceneDetect/OpenCV │
│ 听懂视频              │ 抽取视觉证据            │
│                      │                      │
↓                      ↓
旁白 + 时间戳           关键帧 + 时间戳
                       ↓
                    Qwen3-VL
                       ↓
                  OCR + 场景 + 动作
                       ↓
└───────────────┬───────┘
                ↓
       Python 确定性时间对齐
                ↓
        Raw Unified Timeline
                ↓
          DeepSeek 语义融合
                ↓
          Unified Evidence
                ↓
          DeepSeek 逆向分镜
                ↓
       reverse_storyboard.md
```

---

## 二、当前演示机器基线

当前已经验证通过：

```text
Windows
Python 3.12.10
NVIDIA GeForce RTX 4060 8GB
CUDA Toolkit 12.6
cuDNN 9
CTranslate2 4.8.2

faster-whisper:
large-v3 + CUDA + float16

Ollama:
qwen3-vl:4b-instruct
```

项目目录：

```text
E:\projects\ai-video-ops
│
├── douyin-downloader
│
└── ops-pipeline
```

第三方下载器和公司自己的 Pipeline 保持独立，不修改 `douyin-downloader` 源码。

---

## 三、为了现场演示稳定，推荐这样演

现场第一步可以用一条真实抖音分享链接演示下载。

**从第二步开始，统一使用已经验证通过的“大强创业记”案例。**

这样既能证明下载链路真实可用，也避免现场网络、抖音 Cookie、临时新案例等因素影响后续演示。

固定案例：

```text
Case ID:
7680512578585870322
```

固定视频：

```text
E:\projects\ai-video-ops\douyin-downloader\Downloaded\大强创业记\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322.mp4
```

---

## 四、Step 0｜演示前检查

打开 PowerShell。

确认 GPU：

```powershell
nvidia-smi
```

确认 Ollama：

```powershell
ollama list
```

应该能看到：

```text
qwen3-vl:4b-instruct
```

---

## 五、Step 1｜从抖音分享链接下载案例

进入下载器：

```powershell
Set-Location "E:\projects\ai-video-ops\douyin-downloader"
```

激活它自己的虚拟环境：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

现场粘贴一个真实抖音分享链接：

```powershell
$url = Read-Host "请粘贴抖音分享链接"
```

执行下载：

```powershell
python run.py -c config.yml -u "$url" -t 2 -p ".\Downloaded"
```

打开下载目录：

```powershell
explorer ".\Downloaded"
```

### 演示时展示

理想情况下，一条作品可以得到：

```text
视频 MP4
音乐/原声 MP3
封面 JPG
元数据 JSON
```

### 现场解释

> 这里不是单纯保存视频。  
> 我们把原视频、音乐、封面和原始元数据一起保存，后面所有 AI 分析都有原始证据可以追溯。

下载演示完成后退出 downloader 环境：

```powershell
deactivate
```

---

## 六、Step 2｜进入公司自己的 ops-pipeline

```powershell
Set-Location "E:\projects\ai-video-ops\ops-pipeline"
```

激活 Python 3.12 环境：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

确认：

```powershell
python --version
```

应该是：

```text
Python 3.12.10
```

确认 CUDA 可见：

```powershell
python -c "import ctranslate2; print('CUDA devices:', ctranslate2.get_cuda_device_count()); print('Compute:', ctranslate2.get_supported_compute_types('cuda'))"
```

应该包含：

```text
CUDA devices: 1
float16
```

---

## 七、Step 3｜Whisper：把视频“听懂”

为了避免 GPU 被 Qwen 占用，先释放 Ollama 模型：

```powershell
ollama stop qwen3-vl:4b-instruct
```

执行：

```powershell
python .\scripts\transcribe_case.py `
  --input "E:\projects\ai-video-ops\douyin-downloader\Downloaded\大强创业记\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322.mp4" `
  --model large-v3 `
  --device cuda `
  --compute-type float16
```

### 当前已经验证得到的旁白

```text
这个世界上最好的贵人
就是执行力超强的自己
想做一件事
一定要先去做
哪怕你做的一点都不完美
都没有关系
因为最好的开始
就是一个粗糙的开始
```

### 输出位置

```text
E:\projects\ai-video-ops\ops-pipeline\data\analysis\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\
```

核心文件：

```text
transcript_raw.txt
transcript_segments.json
transcript.srt
case_manifest.json
```

### 演示时解释

> `transcript_raw.txt` 是原始旁白证据。  
> `transcript_segments.json` 不只保存文字，还保存时间戳。  
> 后面 AI 没有权限修改这些原始证据。

---

## 八、Step 4｜抽取视频视觉证据

先清理这条案例之前的视觉实验结果：

```powershell
Remove-Item -Recurse -Force ".\data\visual\7680512578585870322" -ErrorAction SilentlyContinue
```

重新抽帧：

```powershell
python .\scripts\extract_visual_evidence.py `
  --input "E:\projects\ai-video-ops\douyin-downloader\Downloaded\大强创业记\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322.mp4" `
  --interval 1 `
  --keep-duplicates
```

查看结果：

```powershell
explorer ".\data\visual\7680512578585870322\frames"
```

### 演示时解释

> PySceneDetect 负责找到镜头变化，固定时间采样负责兜底。  
> 我们现在宁可多抽候选帧，也不在这里过早丢信息。

当前这条案例约得到：

```text
34 个候选视觉帧
```

---

## 九、Step 5｜Qwen3-VL：把画面“看懂”

当前演示版采用 **8 个代表帧**，而不是一次分析全部 34 张。

运行：

```powershell
python .\scripts\analyze_visual_timeline.py `
  --manifest "E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_evidence_manifest.json" `
  --max-frames 8
```

当前脚本内 `num_ctx` 应为：

```python
"num_ctx": 32768
```

否则这条动态视频的 8 张图片可能超过 16K context。

### 输出

```text
E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_timeline_raw.txt

E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_timeline_frames.json
```

打开分析结果：

```powershell
notepad "E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_timeline_raw.txt"
```

### 演示时重点展示

Qwen 可以识别：

```text
屏幕文字 OCR
人物
动作
环境
餐饮场景
不同镜头变化
视觉时间顺序
```

例如这条视频里可以识别出：

```text
烧烤操作
→ 顾客用餐
→ 市场/采购相关场景
→ 处理食材
→ 街边烹饪
→ 顾客互动
→ 再次烧烤
→ 厨房备料
```

### 当前边界

这里分析的是 **Visual Evidence**。

Qwen 没有拿到音频，所以它不能判断：

```text
视频有没有旁白
```

只能判断：

```text
当前提供的画面中看到了什么
```

---

## 十、Step 6｜Python：确定性音画时间对齐

这一层非常重要。

**时间对齐不交给 AI。**

Audio 路径固定为：

```text
E:\projects\ai-video-ops\ops-pipeline\data\analysis\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\transcript_segments.json
```

执行：

```powershell
python .\scripts\build_evidence_timeline.py `
  --case-id "7680512578585870322" `
  --audio "E:\projects\ai-video-ops\ops-pipeline\data\analysis\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\transcript_segments.json" `
  --visual "E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_timeline_raw.txt" `
  --visual-frames "E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_timeline_frames.json"
```

必须看到：

```text
All audio evidence preserved: YES
```

### 输出

```text
E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\raw_unified_timeline.json
```

### 演示时解释

> 到这一层为止仍然不是让 AI 自己编一份总结。  
> Python 按真实时间戳把 Audio 与 Visual 机械对齐，保证旁白不会丢、时间不会被模型改。

这是后续所有分析的真正时间线底座。

---

## 十一、Step 7｜准备 DeepSeek API Key

**不要把 API Key 写进脚本，也不要显示在 PPT/直播画面中。**

在 PowerShell 中安全输入：

```powershell
$secureKey = Read-Host "请输入 DeepSeek API Key" -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
```

确认环境变量存在，但不显示 Key：

```powershell
if ($env:DEEPSEEK_API_KEY) { "DeepSeek API Key loaded" }
```

应该输出：

```text
DeepSeek API Key loaded
```

---

## 十二、Step 8｜DeepSeek：做音画语义融合

现在 AI **不负责时间、不负责重新写旁白、不负责重新写 OCR**。

它只判断：

```text
声音与画面文字是什么关系？
声音与画面场景是什么关系？
各自承担什么内容作用？
```

执行：

```powershell
python .\scripts\semantic_fuse_timeline.py `
  --input "E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\raw_unified_timeline.json"
```

### 输出

```text
E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\unified_video_evidence.json
```

### 核心分工

```text
Python：
时间 / ID / Evidence 保真

Qwen3-VL：
画面像素 → OCR / 场景 / 动作

DeepSeek：
已经结构化的数据 → 语义关系 / 视频结构理解
```

---

## 十三、Step 9｜DeepSeek：生成逆向分镜

执行：

```powershell
python .\scripts\generate_reverse_storyboard.py `
  --input "E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\unified_video_evidence.json"
```

### 最终输出

```text
E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\storyboard\reverse_storyboard.json

E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\storyboard\reverse_storyboard.md
```

现场直接打开：

```powershell
notepad "E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\storyboard\reverse_storyboard.md"
```

---

## 十四、最终演示成果应该长什么样

最终 Markdown 会得到类似：

| 镜头 | 时间 | 时长 | 旁白 | 画面文字 | 实际画面 | 作用 |
|---|---|---:|---|---|---|---|
| S01 | 0–2s | 2.0s | 这个世界上最好的贵人 | 餐饮创业… | 操作烧烤炉 | Hook |
| S02 | 2–3.6s | 1.6s | 就是执行力超强的自己 | 最好的贵人… | 顾客用餐 | Context |
| S03 | 3.6–6s | 2.4s | 想做一件事 | … | 市场/行走 | Action |
| … | … | … | … | … | … | … |

### 演示时可以这样总结

> 现在我们输入的还是一个普通抖音链接。  
> 最后得到的已经不是视频文件，而是一份机器可以继续学习、人可以直接阅读的分镜资产。  
> 下一步我们可以把几十条同类案例放进来，开始寻找可复用的文案 Pattern 和镜头 Pattern。

---

## 十五、一次演示建议的节奏

### 1. 先展示最终结果

先打开：

```text
reverse_storyboard.md
```

让团队先看到终点。

告诉大家：

> “这份分镜不是人工写的，下面我从一条抖音链接重新走一遍它是怎么来的。”

这样更容易抓住注意力。

### 2. 再现场走完整流水线

顺序：

```text
抖音下载
→ Whisper
→ 抽视觉帧
→ Qwen3-VL
→ Python 时间对齐
→ DeepSeek 融合
→ DeepSeek 逆向分镜
```

### 3. 最后展示原视频与分镜对照

一边播放原视频，一边查看：

```text
reverse_storyboard.md
```

这是整个演示最重要的 Aha Moment。

---

## 十六、当前 MVP 已经跑通的部分

```text
✅ 抖音分享链接解析
✅ 视频下载
✅ 音乐/原声下载
✅ 封面下载
✅ 元数据保存

✅ GPU 高精度旁白转写
✅ 旁白时间戳
✅ 字幕文件

✅ 视频候选关键帧
✅ 屏幕文字 OCR
✅ 人物/动作/环境识别
✅ 多帧视觉 Timeline

✅ Python 确定性音画时间对齐
✅ DeepSeek 音画语义融合
✅ 自动生成逆向分镜
✅ 输出 Markdown / JSON
```

---

## 十七、当前 MVP 的已知限制

### 1. Visual Timeline 当前只分析 8 个代表帧

原视频实际有约：

```text
34 个 Candidate Frames
```

当前只把其中 8 个送给 Qwen。

因此：

```text
主要视觉结构可以识别
```

但：

```text
很短暂出现的字幕或瞬时画面可能漏掉
```

当前分镜属于：

**Representative Storyboard**

还不是：

**Frame-complete Storyboard**

### 2. Whisper 当前以 Segment 为主做展示

虽然原始结果已经保存 Word Timestamp，但当前 Timeline Builder 仍主要使用 Segment。

因此某一句旁白横跨镜头切换点时，最终分镜中可能出现旁白重复。

后续会升级成 Word-level Audio Timeline。

### 3. AI 对镜头作用仍可能过度解释

例如：

```text
处理食材
烹饪
与顾客互动
```

属于可观察到的 Action / Context。

但不一定可以直接标成：

```text
Evidence
```

更不能直接证明：

```text
经营成功
产品优秀
人物创业成功
```

正式 Pattern Mining 前会进一步收紧标签定义。

---

## 十八、距离“完整 AI 短视频代运营工作流”还缺什么

当前完成的是：

# 案例逆向工程 MVP

完整公司工作流还要继续向生产端推进：

```text
案例逆向工程                     ✅ MVP
        ↓
单案例结构理解                    待完善
        ↓
多个案例 Pattern Mining           待实现
        ↓
文案 Pattern 库                   待实现
        ↓
行业镜头 Pattern 库               待实现
        ↓
客户人设
        ↓
AI 生成客户专属文案                待实现
        ↓
AI 生成客户专属分镜                待实现
        ↓
自动生成系统 Excel                 待实现
        ↓
客户按 3–5 秒拍摄素材              人工流程
        ↓
BGM 获取                           部分已具备
        ↓
人声 / BGM 分离                    待实现
        ↓
授权音色 AI 配音                   待实现
        ↓
视频混剪 / 合成                    现有业务系统待全链验证
        ↓
封面 / 发布文案                    待接入
        ↓
自动 / 人工发布                    现有系统待全链验证
        ↓
投流                               人工 SOP
        ↓
真实效果数据回流                    待建立
        ↓
AI 复盘
        ↓
Pattern 强化 / 淘汰                 待实现
```

---

## 十九、如果公司系统今天还没开发完，能不能人工交付？

可以。

当前最终可以演化成：

```text
人工选案例
↓
脚本下载
↓
脚本 ASR
↓
脚本视觉理解
↓
脚本生成逆向分镜
↓
人工筛选高质量案例
↓
AI 提炼 Pattern
↓
客户填写人设
↓
AI 生成文案
↓
AI 生成分镜
↓
Python 输出 Excel
↓
客户拍素材
↓
现有系统制片
↓
人工抽检
↓
发布
↓
投流
↓
人工导出数据
↓
AI 复盘
```

所以产品开发不是这项业务开始运行的前置条件。

产品化的目标是：

**把已经真实跑通的人工 + 脚本 + AI 流程，变成更稳定、更自动、更容易规模复制的生产系统。**

---

## 二十、演示结束时建议用这句话收口

> **今天跑通的不是一个“AI 下载视频”的 Demo。我们验证的是：一条真实短视频，可以被机器听懂、看懂、按时间还原，并最终转化成可复用的文案和分镜资产。接下来，我们要做的是让几十条真实案例共同告诉我们：什么样的文案结构和镜头结构值得复制，再根据每个客户的人设自动生产新的内容。**

---

# 附：完整现场命令速查

## A. 下载

```powershell
Set-Location "E:\projects\ai-video-ops\douyin-downloader"

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

$url = Read-Host "请粘贴抖音分享链接"

python run.py -c config.yml -u "$url" -t 2 -p ".\Downloaded"

explorer ".\Downloaded"

deactivate
```

## B. 进入 Pipeline

```powershell
Set-Location "E:\projects\ai-video-ops\ops-pipeline"

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## C. Whisper

```powershell
ollama stop qwen3-vl:4b-instruct

python .\scripts\transcribe_case.py `
  --input "E:\projects\ai-video-ops\douyin-downloader\Downloaded\大强创业记\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322.mp4" `
  --model large-v3 `
  --device cuda `
  --compute-type float16
```

## D. Visual Frames

```powershell
Remove-Item -Recurse -Force ".\data\visual\7680512578585870322" -ErrorAction SilentlyContinue

python .\scripts\extract_visual_evidence.py `
  --input "E:\projects\ai-video-ops\douyin-downloader\Downloaded\大强创业记\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322.mp4" `
  --interval 1 `
  --keep-duplicates
```

## E. Qwen Visual Timeline

```powershell
python .\scripts\analyze_visual_timeline.py `
  --manifest "E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_evidence_manifest.json" `
  --max-frames 8
```

## F. Deterministic Evidence Timeline

```powershell
python .\scripts\build_evidence_timeline.py `
  --case-id "7680512578585870322" `
  --audio "E:\projects\ai-video-ops\ops-pipeline\data\analysis\2026-09-01_最好的贵人 就是执行力超强的自己. _餐饮创业 _餐饮 _餐饮日常 _创业日记 _餐饮人_7680512578585870322\transcript_segments.json" `
  --visual "E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_timeline_raw.txt" `
  --visual-frames "E:\projects\ai-video-ops\ops-pipeline\data\visual\7680512578585870322\visual_timeline_frames.json"
```

## G. DeepSeek Key

```powershell
$secureKey = Read-Host "请输入 DeepSeek API Key" -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password

if ($env:DEEPSEEK_API_KEY) { "DeepSeek API Key loaded" }
```

## H. Semantic Fusion

```powershell
python .\scripts\semantic_fuse_timeline.py `
  --input "E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\raw_unified_timeline.json"
```

## I. Reverse Storyboard

```powershell
python .\scripts\generate_reverse_storyboard.py `
  --input "E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\unified_video_evidence.json"
```

## J. 打开最终结果

```powershell
notepad "E:\projects\ai-video-ops\ops-pipeline\data\unified\7680512578585870322\storyboard\reverse_storyboard.md"
```

---

**Status：MVP Demo Ready**

当前版本适合内部演示和继续脚本验证，不作为最终生产级 Pipeline 冻结版本。
