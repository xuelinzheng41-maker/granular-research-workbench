# 独立验收指南

需要 Python 3.10+。从技能目录执行；无需组内知识库、第三方 Python 包或模型密钥。以下是合成验收案例，不是科研创新案例。

## A. 开箱验收

~~~bash
python -B scripts/selftest.py
python -B scripts/shortlist.py examples/brief.json
python -B scripts/replay.py prepare verification-run
~~~

比较示例合法地返回空的 `eligible_ids`：图论题是教材练习，事件流题未完成近邻核查。`eligible_for_probe` 也只表示可以尝试小验证，不是允许立项。`prepare` 必须使用尚不存在的目录，现场创建四个候选，验证没有复核就不能生成正式草稿。两类数据分别是图的边表、按顺序到达的带真值事件流；不需要下载数据。

## B. 独立复核和揭晓

1. 只把 `verification-run/review-packet.json` 发给另一位研究者。不要先看或转交 [参考裁决](examples/reference-review.json)。让对方根据边表或事件流手算一项关键读数，再核对报告。没有人手时可用干净模型会话试跑，并记录模型和是否用工具；不能代替独立的人类验证。
2. 复核者按下方格式交回 JSON，四个 case 都要填。判定取 `direct`（直接支持限定主张）、`proxy_only`（仅有相关或较弱证据）、`insufficient`（关键材料缺失）、`contradicted`（同条件下有反例）。摘要照抄该 case 的 `review_input_sha256`，不是另算。`reviewer_type`（`human`/`ai_agent`）和 `author_result_exposure`（`none`/`seen`）是自我声明，可留空或写 `unspecified`；工具不验证身份，缺字段不会被当作盲审。回放生成的材料包本就不含作者结果，但仍应据实声明。

~~~json
{
  "case-a": {
    "reviewer": "复核者编号",
    "reviewer_type": "human 或 ai_agent",
    "author_result_exposure": "none 或 seen",
    "verdict": "填写实际判定",
    "evidence_location": "点出原始材料的可复算位置",
    "rival_check": "解释最强替代解释是否仍成立",
    "reason": "写明核算读数或推理和对应范围",
    "review_input_sha256": "从同一 case 的材料包粘贴"
  }
}
~~~

~~~bash
python -B scripts/replay.py finish verification-run verdicts.json
~~~

上述命令按实际裁决执行 `probe.py check` 和 `kb.py scaffold`，再写出 `verification-run/replay-report.json` 对照参考答案。分别报告流程成功数和裁决一致数；退出 `1` 表示裁决有偏差，`2` 表示输入或流程出错。只有 `direct` 会生成三件套。若有分歧，回查证据，不要改答案来凑通过率。重做须用新的运行目录。摘要只防止误用旧复核，不能证明身份、时间顺序或不可篡改性。

## C. 用新题验证有效性

**这不是上面四个例子的重跑。** 请不参与开发的同学给出他们真实在考虑的数学或 CS 课题，提前隔离题目及评审标准；至少涵盖两类题型，并保留全部起始题（包括没有推进候选的题）。步骤如下：

1. 先记录题目、可用数据与设备、技能、可用工时、每个探针的上限。选定同一个模型、时间及检索权限；同题各跑两个新的独立会话。一组直接要求找可行选题，另一组使用技能，轮换先后顺序。双方用同样的答复格式和探针预算，记录超时和没产出。
2. 统一匿名材料：一条核心主张、最近工作及链接、当前原始证据、替代解释、下一周可完成的动作。去掉技能版本、模板样式、作者及组别。未核实的文献差异要标明；不能因没有检索到就称为创新。
3. 由未参与生成的人分别裁决“值得再投入一周 / 仅缺限定证据 / 停止”。复核重点是贡献是否有区分、学生是否做得动、证据是否真的回答问题。抽查人工复算和原文。分歧先记录，必要时由第三人复核，再揭晓分组。
4. 主指标按**全部起始题**计算“至少有一个值得投入下一周的候选”的比例；同时记录误放（材料不配却放行）、误拦（有直接证据却拦下）、用时和无产出。结果小样本、领域单一或同模型评审时，不推广为总体效果。

留档可使用 [新题验证记录模板](templates/validation-trial.md)。本指南不是正式预注册；如果后续要正式做效果研究，在对应研究开始前另走独立、可核验的登记流程。不要在报告中把演练或内部时间戳称作正式预注册。
