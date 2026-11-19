# 科研选题助手（Research Idea Skill）中文指南

适合数学和计算机学生从文献空位、可核对的反常或跨领域机制出发，筛出值得继续验证的候选。当前技能版本：**v1.5.0**。已有原始材料的独立复验从 [验收指南](VALIDATION.zh.md) 开始。

## 安装与自测

需要 Python 3.10 或更新版本。在技能目录运行：

~~~bash
python scripts/selftest.py
~~~

默认测试使用包内样例，无需知识库、网络或第三方 Python 包。有兼容的论文卡、语料及已有提案时，可配置 `LAB_KB`、`LAB_DATA`、`LAB_IDEAS`，再运行 `python scripts/selftest.py --with-kb`。经 GitHub 克隆或解压使用时，候选默认写入当前目录下的 `ideas/`，可用 `LAB_IDEAS` 指定其他目录。

## 从候选到提案

先按 [候选输入示例](examples/brief.json) 记录本周工时、技能、数据与设备，并填写每条候选的最近工作、最大风险和最小验证。运行 `python scripts/shortlist.py <比较记录.json>`；没有满足条件的候选可以留空，不强推。

1. 运行 `python scripts/kb.py draft my-topic`。记录命令输出的候选 ID 和目录。
2. 填写计划：一条核心主张、适用范围、最强替代解释、对照和停止条件。先制定计划，再做小验证。数学题可以做构造或检查引理；实验题要留存对照、口径及原始读数。
3. 填写结果，写清证据实际支持的范围。作者填 `advance` 只是建议，须将 `submitted_for_review` 设为 `true`；交给未参与生成的人按[复核指南](references/review-protocol.md)核查。复核若发现只测了较弱命题或代理指标，先缩小主张后重审，或暂缓。
4. 运行 `python scripts/probe.py check ideas/<ID>`。返回 `0` 后，再运行 `python scripts/kb.py scaffold <ID>` 生成提案草稿。`2` 表示记录缺失或不匹配，`3` 表示暂缓或反驳。把 `<ID>` 换成实际 ID；使用自定义产出目录时，以 `draft` 打印的目录为准。
5. 按[检查清单](references/checklists.md)完善提案。有库用原始论文卡复核；无库可运行 `python scripts/grade.py --external ideas/<ID>` 辅助检查格式线索与文档结构，不能判断科学证据是否可靠。接入含 YAML 元数据的本地论文卡时，需先运行 `python -m pip install PyYAML`；无库流程不需要安装。

## 继续阅读

- [技能完整流程](SKILL.md)
- [数学与理论方向](references/domain-theory-math.md)
- [计算机实验方向](references/domain-experimental-cs.md)
- [探针与推进判定](references/probe-first.md)

评分不代表发表质量。工具不认证复核者身份，也不会自动上传材料；复核摘要用于核对材料版本，不等于正式预注册。未得到授权时，不要向第三方模型上传内部数据。
