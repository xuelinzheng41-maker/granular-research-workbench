# 粗糙集与粒球研究工作台

第一版在本机运行，覆盖「领域文献 → 候选比较 → 数学或实验验证 → 独立复核」。不包含论文撰写，不访问云端项目，不上传研究材料。

## 从哪开始

- [研究入口](SKILL.md)：供助手执行，规定两条路线、推进条件和交接方式。
- [领域定义与历史实验索引](domain/definitions.md)：粗糙近似的两种情形和 GBSK 历史复现的证据边界。
- [选题模块](../skills/research-idea/README.zh.md)：已校验并原样解包的 v1.5，含候选约束比较、文献与证据复核方法。

## 本地复跑

在本目录运行。数学线用 Python 3.10+ 标准库。实验线使用本机已验证的 NumPy、scikit-learn 和其依赖；Digits 随库提供，无需下载。复算会报告 Python、NumPy 和 scikit-learn 的版本差异；仅版本标签不同不阻断，数据指纹、切分、逐样本预测或其他证据不同仍失败。旧版清单不自动升级，保留原记录并使用原运行器，或在新目录重新运行。

~~~powershell
python -B ../skills/research-idea/scripts/selftest.py
python -B workbench.py math runs/covering-refinement
# 安装 scikit-learn 后运行实验示例：
python -B workbench.py digits runs/digits-prototypes
python -B workbench.py verify runs/covering-refinement
python -B workbench.py verify runs/digits-prototypes
python -B workbench.py review-input runs/covering-refinement
~~~

已有运行不会被覆盖。需要重跑时使用新的输出目录。每次生成探针计划、逐项证据、作者结论和 SHA-256 清单。前三者进入清单，可编辑的独立复核记录不在其中。摘要可检出后续变动，不能证明记录时间或复核身份。

| 路线 | 实际输出 | 当前解释 |
| --- | --- | --- |
| 数学 | 三点覆盖及 96 项有限检查 | 每个细块都包含于某个粗块，但目标下近似由 {0,1} 变为 {0}。覆盖命题不成立；划分情形另有一般证明。 |
| 实验 | Digits 三个切分的逐样本输出 | 原型替代的损失分别为 0.44、3.33、8.22 个百分点；两个切分超过事先设定的 3 点上限。只否定当前有限主张，不否定粒球方法整体。 |

## 请另一位研究者复核

先把相应运行目录的计划和原始证据交给对方；Windows 上可直接用上方命令复算。复核人自行记录「哪条主张、证据位置、还能否由替代解释解释」，按 [复核规范](../skills/research-idea/references/review-protocol.md) 填该运行的复核记录和摘要，再执行：

~~~powershell
python -B workbench.py check runs/covering-refinement
~~~

`submitted_for_review` 仅表示送审，`status` 记录作者结论。两个示例都触发停止条件，因此写 `refuted`，但仍可送审。`check` 缺复核或作者与复核者意见冲突时返回 2；记录正确且驳回或暂缓时返回 3；只有作者建议推进且复核认为有直接证据时才返回 0。运行器不代填复核，也不自动写提案。

在仓库根目录执行 `python -B -m unittest discover -s workbench/tests -v` 可运行工作台回归；未安装 scikit-learn 时跳过 Digits 测试。

## 带自己的题

按 [研究任务模板](templates/study.md) 记录问题与预算，从 [候选输入示例](../skills/research-idea/examples/brief.json) 开始比较。选定候选后，走[候选交接流程](../skills/research-idea/references/probe-first.md#从筛选结果交接到实现)，锁定主张、预算和停止条件，再实现、封存和送审。以上两个运行器是可复算的基准案例，不是任意数学主张或实验配置的自动求解器。开始任何确认性研究前，另行决定是否需要正式预注册。
