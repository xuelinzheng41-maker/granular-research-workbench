# 粗糙集与粒球研究工作台

第一版在本机运行，覆盖「领域文献 → 候选比较 → 数学或实验验证 → 独立复核」。不包含论文撰写，不访问云端项目，不上传研究材料。

## 从哪开始

- [研究入口](SKILL.md)：供助手执行，规定两条路线、推进条件和交接方式。
- [领域定义与历史实验索引](domain/definitions.md)：粗糙近似的两种情形和 GBSK 历史复现的证据边界。
- [选题模块](../skills/research-idea/README.zh.md)：已校验并原样解包的 v1.5，含候选约束比较、文献与证据复核方法。

## 本地复跑

在本目录运行。数学线用 Python 3.10+ 标准库。实验线使用本机已验证的 NumPy、scikit-learn 和其依赖；Digits 随库提供，无需下载。跨环境的数值复算请先核对运行产物里的 Python、NumPy 和 scikit-learn 版本。

~~~powershell
python -B ../skills/research-idea/scripts/selftest.py
python -B workbench.py math runs/covering-refinement
# 安装 scikit-learn 后运行实验示例：
python -B workbench.py digits runs/digits-prototypes
python -B workbench.py verify runs/covering-refinement
python -B workbench.py verify runs/digits-prototypes
python -B workbench.py review-input runs/covering-refinement
~~~

已有运行不会被覆盖。需要重跑时使用新的输出目录。每次生成探针计划、逐项证据和 SHA-256 清单。摘要可检出后续变动，不能证明记录时间或复核身份。

| 路线 | 实际输出 | 当前解释 |
| --- | --- | --- |
| 数学 | 三点覆盖及 96 项有限检查 | 每个细块都包含于某个粗块，但目标下近似由 {0,1} 变为 {0}。覆盖命题不成立；划分情形另有一般证明。 |
| 实验 | Digits 三个切分的逐样本输出 | 原型替代的损失分别为 0.44、3.33、8.22 个百分点；两个切分超过事先设定的 3 点上限。只否定当前有限主张，不否定粒球方法整体。 |

## 请另一位研究者复核

先把相应运行目录的计划和原始证据交给对方；Windows 上可直接用上方命令复算。复核人自行记录「哪条主张、证据位置、还能否由替代解释解释」，按 [复核规范](../skills/research-idea/references/review-protocol.md) 填该运行的复核记录和摘要，再执行：

~~~powershell
python -B workbench.py check runs/covering-refinement
~~~

没有复核时返回 2；记录正确且驳回/暂缓返回 3；只有直接支持返回 0。为让独立复核者作出判定，运行器将兼容字段 `status=advance` 用作提交审查状态，不代表作者宣布主张成立。运行器不代填复核，也不自动写提案。

## 带自己的题

按 [研究任务模板](templates/study.md) 记录问题与预算，从 [候选输入示例](../skills/research-idea/examples/brief.json) 开始比较。另建运行目录写自己的计划和原始证据，直接用选题模块的探针命令。以上两个运行器是可复算的基准案例，不是任意数学主张或实验配置的自动求解器。开始任何确认性研究前，另行决定是否需要正式预注册。
