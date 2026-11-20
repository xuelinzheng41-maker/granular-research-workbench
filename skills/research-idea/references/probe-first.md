# 先探针，再立项

## 候选从哪里来

先按 [快速上手](../README.md) 配置工作目录。文中的 `ideas/<ID>` 指该次 `draft` 打印的实际目录。

每轮先比 2–3 条候选，至少尝试两种来源，并记下落选理由。实在只有一种来源就写明，别为凑数编造。

| 来源 | 记录什么 | 先排除什么 |
|---|---|---|
| 文献空位（literature） | 原文做了什么；这个空位影响谁的哪项决策 | 只因没人做；已证伪/已有等价工作 |
| 反常（anomaly） | 原预期及出处、实际读数/反例、适用条件、竞争解释 | 数据、指标、参数、实现版本、基线不一致 |
| 跨域迁移（transfer） | 原机制、可复用的不变量、在哪个目标假设下会失效 | 术语相像但假设不相容 |

GitHub 可选：只追与问题直接相关的官方实现、可复现 issue、benchmark 或具体修复。记下 permalink/commit、复现条件和维护者结论；stars、fork、未关闭 issue 都不能证明新颖性或影响。证据需要回到实验、原文或独立复核。

## 从筛选结果交接到实现

按下面的顺序，从技能目录执行。以 `draft` 输出的实际目录替换 `ideas/<ID>`：

~~~bash
python scripts/shortlist.py brief.json
python scripts/kb.py draft my-probe --brief brief.json --candidate selected-id
# 补齐探针计划，然后锁定计划：
python scripts/probe.py freeze ideas/<ID>
# 按已锁定的计划执行实验或写出可检查的证明，再填写作者结果：
python scripts/probe.py seal ideas/<ID>
python scripts/probe.py review-input ideas/<ID>
# 独立复核者完成检查并填写复核记录后：
python scripts/probe.py check ideas/<ID>
~~~

`draft` 重新检查候选资格。候选 ID、主张、预算和推进/停止条件从候选比较记录继承，不在探针中另填。补齐对象、对照，以及 `implementation.path` 和 `implementation.reproduce`（命令或证明核查步骤）；冻结后再执行。将 `freeze` 输出的 `plan_sha256` 填入结果的 `frozen_plan_sha256`，并在 `artifacts` 中列出实现或证明文件，以及至少一份独立的原始证据文件。复核者按说明手工核查或自行运行，工具不会自动执行任意命令。

封存后若改变主张、对照或证据，请在新目录重做交接并重新送审。清单只能检查记录一致性，不证明命令何时运行或复核者身份；复核记录里的 `reviewer_type` 与 `author_result_exposure` 同样只是声明。旧记录缺少这两个字段时按 `unspecified` 显示，不当作盲审，也不阻止已有记录继续使用。候选目录包含比较记录快照；只与获准查看这些材料的人共享。

## 正式复跑前锁定实现和输入

要将探索版转为正式比较，在冻结计划前，在 `implementation` 中增加 `inputs`，列出候选目录内的依赖脚本、切分清单、配置或本地数据文件（实现入口自动纳入；仅锁入口时用 `[]`）。计划仍可先于代码冻结。等代码和输入准备好、正式执行前，运行：

~~~bash
python scripts/probe.py lock-inputs ideas/<ID>
# 复核者在任何时刻均可只读重算，不改动锁或输入：
python scripts/probe.py verify-inputs ideas/<ID>
~~~

命令按文件内容生成输入清单，缺文件或文件不在候选目录内会报错。把输出中的 `inputs_sha256` 填入结果的 `frozen_inputs_sha256`；送审时同时交付输入锁清单和可读取的输入。正式运行产生的证据要与锁定输入分开。实现或输入发生变化时，`seal`、`review-input` 和 `check` 不会沿用原记录；新版本使用新候选目录。未声明 `implementation.inputs` 的旧记录保持原行为，不会被视为在运行前已锁输入。

`verify-inputs` 只读核对记录之间的一致性：重新计算锁中声明的文件哈希，并检查当前 `probe-plan.json` 的摘要是否仍等于锁中的 `plan_sha256`（`plan_changed`，变化时附 `current_plan_sha256`），以及锁自身的 `inputs_sha256` 是否等于由锁中除 `inputs_sha256` 外的全部字段重算出的摘要（`lock_integrity`）；锁的顶层字段必须恰好是 `plan_sha256`、`files` 和 `inputs_sha256`，出现任何其他字段都视为完整性失败。全部匹配时退出 0，输出 `ok`、`plan_sha256`、`inputs_sha256`、`plan_changed: false`、`lock_integrity: true` 和当前 `files`；计划或文件变动、缺失、锁与当前声明不一致、锁自身摘要不一致或锁含未知顶层字段时退出 3，并在 `changed`、`missing`、`extra` 中标出差异。输入锁不存在或计划属于未声明 `implementation.inputs` 的旧记录时退出 2，提示先补齐声明并运行 `lock-inputs`；命令不会创建、修复或删除任何文件。它核对的是记录一致性，不证明某条命令实际读取了哪些文件、何时执行，也不证明是谁运行了什么、运行环境或外部数据未被替换。

这里锁定的是声明的文件，不证明实际命令、执行时刻或文件选择。若通过候选目录内的清单引用外部数据，本工具只核对清单本身；复核还要独立核对外部数据哈希及环境。

## 最小探针（兼容已有记录）

1. 开候选目录：

   ~~~bash
   python scripts/kb.py draft short-name
   # 将下方 <ID> 替换成 draft 打印的目录名；也可用 LAB_IDEAS 指向其他根目录。
   python scripts/probe.py plan ideas/<ID>
   ~~~

2. 先填计划再测。`question` 是研究问题；`core_claim` 是这轮决定推进的唯一主张，可比长期研究目标窄。写明适用范围、最强竞争解释、对照、继续/停止条件和预算。建议单候选 30 分钟；没有达到任何判据或预算不足，记为不确定。
3. 实验型：使用新切片、新种子或独立的受控小例，注明输入、运行命令、数据切分、基线、版本和原始读数。发现异常的材料不能同时充当独立复核。定理型：明确对象/量词/假设；可以手算小反例、穷举小规模、构造例或验证关键引理。不要求数据集。搜不到反例不算证明，只有有限枚举也不得支持全称结论。
4. 作者填 `probe-result.json`。`supported_claim` 写证据实际支持的最强陈述，不写未来计划。把最小证据留在候选目录，例如 `evidence/notes.md`；缓存放 `scratch/`。`status` 记录作者结论（`advance`、`refuted` 或 `inconclusive`），`submitted_for_review` 独立记录是否送审。建议推进必须设为 `true`；反驳或暂缓也可送审，未送审则可用 `check` 归档。送审时运行：

   ~~~bash
   python scripts/probe.py review-input ideas/<ID>
   ~~~

5. 把计划、实际证据和首轮材料包交给另一位同学，或不参与生成的独立审查会话。`review-input` 默认只给冻结主张、复验条件、证据引用和复核摘要，不含作者结果；复核者先独立检查核心主张、适用条件、对照和原始证据并记录自己的判断，再按需加 `--full` 查看作者结果，并在 `probe-review.json` 声明 `reviewer_type` 和 `author_result_exposure`；按 [复核说明](review-protocol.md) 填写其余字段。没有独立复核就保留候选，不自行补填。

   ~~~bash
   python scripts/probe.py check ideas/<ID>
   python scripts/kb.py scaffold <ID>
   ~~~

6. 继续前还要确认：谁会因结果改变哪项决策？现有资源能否支撑接下来 1–2 周的目标？何时停止投入？初证不是正式确认。

| 复核判定 | 怎么办 |
|---|---|
| `direct` | 证据在计划限定的范围内直接检验核心主张，并满足推进条件；作者也建议推进才可写提案，不等于已证实或有新颖性。 |
| `proxy_only` | 只验证代理指标、弱命题或贡献链中的一环。暂缓，或保留旧记录、缩小主张后重审。 |
| `insufficient` | 缺数据、超时、对照异常、证据处在灰区或只是复述发现样本。暂缓。 |
| `contradicted` | 证据直接反驳核心主张。归档负面结果，不生成正式提案。 |

盲测 C2：相同簇数轨迹下，点对断差能区分两条链；但目标层和命中率没有检验。这对“能更准确恢复目标层”只能判为 `proxy_only`。

工具核对记录和证据版本，不判断科学结论，也不认证复核者身份。计划、结果或引用证据变化后必须重审；摘要不提供可信时间戳或防篡改，不是正式生死判预注册。历史提案仍可照常评分，不补记为通过。
