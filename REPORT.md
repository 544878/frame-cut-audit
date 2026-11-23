# Frame Cut Audit v0.1.0

## 中文｜成片切点验收报告

导出完成后，剪辑者可以用 Frame Cut Audit 核对成片是否保留了计划中的画面。给 Agent 原片、成片和剪辑清单。它会指出每段在原片里的实际起止位置，并把回看链接放进报告。

### 怎么核对

1. 剪辑清单按成片顺序列出要保留的原片区间，单位为秒。每段包含起点帧，结束位置是第一帧不保留的画面。
2. FFmpeg 解码原片和成片，为每帧的像素生成一串校验值，也叫帧指纹。脚本先用只在原片出现一次的帧定位，再逐帧确认整段和拼接处。
3. 脚本对比计划与实际起止帧。清单时间落在两帧之间时，以该时刻之后的第一帧为准。偏差为负数表示实际切点在原片上更早。

浏览器报告 `audit.html` 提供成片回看链接。数据文件 `audit.json` 记录原片和成片的时间区间、帧编号和偏差，便于脚本读取。实测区间数与计划不一致时，报告分别列出两份区间。画面无法唯一定位时，报告给出原因并标记为需要复核。

### 实测结果

用 Python 3.9.6 和 FFmpeg 7.0 运行 v0.1.0。测试原片由 FFmpeg 生成，每秒 8 帧。两段成片通过复制视频轨拼接。

| 片段 | 计划区间（原片） | 实际区间（原片） | 结果 |
| --- | --- | --- | --- |
| 第 1 段 | 4.500–6.000 秒 | 4.000–6.000 秒 | 开头早了 0.500 秒（4 帧），结尾一致 |
| 第 2 段 | 0.000–2.000 秒 | 0.000–2.000 秒 | 开头与结尾均一致 |

两段样例的整体结果为「有偏差」。另外，自动验收脚本的 8 项测试全部通过，覆盖准确剪切、开头切早、结尾切早、换序拼接及回看链接、缺段、相邻片段合并、画面重复和无效清单。

### 适用范围

首版检查单一原片和一份成片，适合直接复制视频轨、画面像素保持一致的剪切。重新编码改变像素、缩放、加特效，或重复画面让拼接位置不明确时，需要人工复核。真实剪辑项目仍待验证，音频同步超出本版的检查范围。

## English | Export cut audit report

After export, editors can use Frame Cut Audit to check which parts of the source the export kept. Give the agent the source video, the export, and the cut list. The report shows the measured source boundaries and includes links to replay the export.

### How the audit works

1. List the source ranges to keep, in export order, with times in seconds. Each range includes its start frame and ends before the first excluded frame.
2. FFmpeg decodes both videos and makes a fingerprint from the pixels of each frame. The script uses frames that occur once in the source to find each range. It then checks each frame and each join.
3. The script compares the planned and measured frame boundaries. If a requested time falls between two frames, it uses the first frame after that time. A negative difference means the measured boundary occurs earlier in the source.

Open `audit.html` for replay links. Read `audit.json` for source and export ranges, frame indices, and differences. If the range counts differ, the report lists the planned and measured ranges separately. If the script cannot find a unique match, it gives the reason and requests manual review.

### Test results

Frame Cut Audit v0.1.0 ran with Python 3.9.6 and FFmpeg 7.0. FFmpeg made the test source at 8 frames per second. The two parts of the export were joined by copying the video stream.

| Excerpt | Planned source range | Measured source range | Result |
| --- | --- | --- | --- |
| 1 | 4.500–6.000 s | 4.000–6.000 s | Start 0.500 s early (4 frames). End matches. |
| 2 | 0.000–2.000 s | 0.000–2.000 s | Start and end match. |

The two-part export returned “Cut differences found.” All eight automated cases also passed. They cover exact cuts, early starts, early ends, reordered joins with replay links, missing ranges, adjacent ranges, repeated frames, and invalid cut lists.

### Scope

This version checks one source and one export. It works with stream-copy cuts that preserve decoded pixels. Encoding changes, scaling, effects, or repeated frames at a join can require manual review. A real editing project still needs verification. Audio sync is outside the scope of this version.

## 复现命令 / Reproduction commands

在 Skill 根目录运行。Run from the Skill root.

```sh
python3 tests/e2e.py
```

检查自己的成片。Check your own export.

```sh
python3 scripts/cut_audit.py source.mp4 export.mp4 cuts.csv --output audit-run
```

`cuts.csv` 示例 / Example

```csv
start,end,label
4.5,6,First excerpt
0,2,Second excerpt
```

| 退出码 / Exit code | 中文 | English |
| --- | --- | --- |
| `0` | 实际区间符合计划 | Matches the plan |
| `1` | 切点或连续区间数有偏差 | A boundary or range count differs |
| `2` | 输入或运行出错 | Input or execution error |
| `3` | 画面无法唯一匹配，需复核 | Frame matching needs manual review |
