# 科研选题助手（Research Idea Skill）

详细使用说明见 [中文指南](README.zh.md)；第三方从原始材料复跑数学与计算机案例，请从 [独立验收指南](VALIDATION.zh.md) 开始。

v1.5.0 面向数学与计算机学生：先按资源和证据取舍候选，再用小实验或构造试探，由他人复核。工具无需组内知识库、模型密钥或网络，不保证新颖性，也不代替正式验证。

## 开箱自测

需要 Python 3.10+。在解压后的目录运行：

~~~text
python scripts/selftest.py
~~~

默认只使用包内测试材料。有兼容的论文卡、语料和已有提案时，设置 `LAB_KB`、`LAB_DATA`、`LAB_IDEAS` 后使用 `python scripts/selftest.py --with-kb`；该模式会检查真实库，没有知识库就不应使用。

## 从候选到草稿

Linux / macOS：`export LAB_IDEAS="$(pwd)/ideas"`；Windows PowerShell：`$env:LAB_IDEAS = Join-Path (Get-Location).Path 'ideas'`。也可设为包外的可写目录。下文用 `ideas` 表示它。建议先读 [六步流程](SKILL.md)，按题型选 [数学](references/domain-theory-math.md) 或 [计算机实验](references/domain-experimental-cs.md)。

1. 运行 `python scripts/kb.py draft my-topic`。输出的日期加短名是候选 ID。在产生新证据前，填计划的核心主张、适用范围、最强替代解释、对照和停止条件。
2. 执行小探针并保留原始算例、读数或推导。填写结果里的实际支持范围，不能把未来验证计划写成证据。作者填写 `advance` 后，还需由另一位同学按 [复核说明](references/review-protocol.md) 审查。
3. 运行 `python scripts/probe.py check ideas/<ID>`；只有通过才运行 `python scripts/kb.py scaffold <ID>`。替换示例中的整段 `<ID>` 为实际候选 ID。状态码：`0` 可写草稿，`2` 记录缺失/不匹配，`3` 暂缓或已反驳。
4. 用 [检查清单](references/checklists.md) 写正式草案。有库用原始论文卡复核；无库时可用 `python scripts/grade.py --external ideas/<ID>` 检查格式与证据纪律。分数不代表科学或发表质量。

组内分发版只含通用工具、模板和合成测试。系统不验证复核人身份，也不会自动把材料发给模型。不要把受限数据交给未授权第三方。新填的 `direct` 复核必须标出证据位置和替代解释；旧提案可照常评分，旧的推进记录重新落地时要补复核字段。
