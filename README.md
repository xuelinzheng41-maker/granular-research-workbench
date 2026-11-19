# 粗糙集与粒球研究工作台

从文献和定义出发，筛出值得试的选题，用**数学证明或反例**、**可重跑的计算实验**验证，再交给另一位研究者复核。面向粗糙集、粒球及相关数学与计算机研究；当前不包含论文写作。

**本地可跑：** Python 3.10+。选题自测和数学示例只用标准库；Digits 示例需要 NumPy 和 scikit-learn，数据随库提供。以下命令均从仓库根目录执行。

## 研究入口

| 我想做什么 | 直接入口 | 产物或判定 |
| --- | --- | --- |
| 核对粗糙集与粒球的定义和基线 | [领域定义与复现边界](workbench/domain/definitions.md) · [研究任务模板](workbench/templates/study.md) | 算子、假设、对照与证据口径 |
| 从几条想法中挑能做的题 | [候选筛选脚本](skills/research-idea/scripts/shortlist.py) · [输入示例](skills/research-idea/examples/brief.json) | 合格候选、暂缓原因和最小验证 |
| 查论文卡、近邻工作与反例 | [知识库工具](skills/research-idea/scripts/kb.py) · [反例检索工具](skills/research-idea/scripts/refute.py) | 文献锚点、已有反证和检索范围 |
| 核查数学主张 | [数学路线](skills/research-idea/references/domain-theory-math.md) · [工作台运行器](workbench/workbench.py) | 有限反例、证明思路、可复算清单 |
| 跑受控的计算实验 | [实验路线](skills/research-idea/references/domain-experimental-cs.md) · [工作台运行器](workbench/workbench.py) | 逐种子、逐样本输出与去留条件 |
| 复算证据、独立裁决 | [复核规范](skills/research-idea/references/review-protocol.md) · [盲审回放器](skills/research-idea/scripts/replay.py) | 材料摘要、复核意见、推进或停止 |

[工作台 Skill](workbench/SKILL.md)负责串联研究流程；[选题 Skill v1.5](skills/research-idea/SKILL.md)可单独使用。不需要云端服务或私有知识库才能运行下面的示例。

## 1. 找文献，比较候选

从文献空位、可核对的反常或跨域迁移提出候选，把最接近的工作、主要差异、替代解释和最小验证放在一张比较表里。筛选时检查学生的时间、技能、数据与算力；允许最终一个题都不推荐。

~~~bash
python -B skills/research-idea/scripts/selftest.py
python -B skills/research-idea/scripts/shortlist.py skills/research-idea/examples/brief.json
python -B skills/research-idea/scripts/kb.py draft my-topic
~~~

比较示例返回空的 `eligible_ids`：图论题是已知性质的练习，事件流题尚未完成近邻检索。`draft` 会打印候选地址并创建探针记录，并不生成正式提案。

接入兼容的本地知识库后，可用下列入口。无库时用可核对的原文，记下搜索词、覆盖范围和最近工作；没找到重合不等于证明新颖。

~~~bash
python -B skills/research-idea/scripts/kb.py doctor
python -B skills/research-idea/scripts/kb.py anchors "covering rough sets" --n 5
python -B skills/research-idea/scripts/refute.py "refinement" "lower approximation" --limit=5
~~~

## 2. 数学验证：覆盖细化的三点反例

**问题：** 每个细块包含在某个粗块里，粗下近似是否必然包含于细下近似？固定下近似为「所有包含于目标集的块的并」，然后核对：

| 宇宙与目标 | 粗覆盖 → 细覆盖 | 下近似 |
| --- | --- | --- |
| 宇宙 {0,1,2}；目标 {0,1} | {{0,1},{1,2}} → {{0},{1,2}} | {0,1} → {0} |

这一个反例足以反驳覆盖情形的全称主张。运行器另检查三点宇宙上的 **96 次检查（12 组细化对 × 8 个目标集）**；划分情形的[一般证明思路](workbench/domain/definitions.md#数学线有限清晰覆盖)不依赖这 96 项枚举。

~~~bash
python -B workbench/workbench.py math workbench/runs/covering-refinement
python -B workbench/workbench.py verify workbench/runs/covering-refinement
~~~

## 3. 计算实验：Digits 原型替代

**问题：** 在三个固定留出切分上，把样本替换为最近的训练原型，准确率是否每次都只损失至多 3 个百分点？两臂共用切分、距离和分类器，只改变预测输入。每个切分 450 个测试样本，保存真值、预测、原型索引和数据指纹。

| 种子 | 原样本预测正确数 | 原型替代预测正确数 | 准确率损失 |
| --- | ---: | ---: | ---: |
| 11 | 413 | 411 | 0.44 个百分点 |
| 29 | 402 | 387 | 3.33 个百分点 |
| 47 | 417 | 380 | 8.22 个百分点 |

**结果：两个切分超出阈值，当前有限主张不成立。** 这是粒球原型替代的机制筛查，不是 GBSK 复现，也不能据此否定自适应粒球方法。接入历史 GBSK 实验时，须把原版、插桩与 M-means 变体分开，先确认输入身份，再比标签、ACC/ARI 与 Key Ball 数；[口径说明](workbench/domain/definitions.md)已列明。历史实验原始数据不随工作台分发。

~~~bash
python -m pip install scikit-learn
python -B workbench/workbench.py digits workbench/runs/digits-prototypes
python -B workbench/workbench.py verify workbench/runs/digits-prototypes
~~~

## 4. 交给别人复算和裁决

数学与实验运行都会生成探针计划、原始证据、SHA-256 清单和空白复核记录。先复算，再把材料交给未参与生成的人，填写证据位置、替代解释和裁决。只有直接支持限定主张才放行；暂缓和反驳都保留记录。摘要能检出材料变更，不认证身份，也不能代替正式预注册。

~~~bash
python -B workbench/workbench.py review-input workbench/runs/covering-refinement
# 独立复核者填写该次运行的 probe-review.json 后执行：
python -B workbench/workbench.py check workbench/runs/covering-refinement
~~~

还可以用内置的四个合成候选走一次盲审：从原始图边表或事件流重算，把生成的复核材料交给另一位研究者，先记录裁决，再揭晓参考判定。

~~~bash
python -B skills/research-idea/scripts/replay.py prepare verification-run
python -B skills/research-idea/scripts/replay.py finish verification-run verdicts.json
~~~

**当前验证：** 无库技能自测和工作台回归分别运行。两条工作台案例可生成并复算，另有四个合成案例用于检验复核回放；裁决与参考一致不证明独立盲审。这验证的是流程和复核样例，不代表真实选题成功率已有提升。带新题做对照可直接用[验证记录模板](skills/research-idea/templates/validation-trial.md)；细节见[工作台指南](workbench/README.md)和[独立验收指南](skills/research-idea/VALIDATION.zh.md)。
