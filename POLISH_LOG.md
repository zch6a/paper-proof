# paper-proof：开发与打磨日志

## 开发（2026-11-13）

- 参考文献核查：BibTeX 解析；按 DOI / arXiv 号精确查，再按标题查 Semantic Scholar、OpenAlex、Crossref、arXiv；查无此文 / 信息不符 / 已撤稿 / 预印本已正式发表 / 重复条目；两个数据库应答了都没有才算“查无此文”，否则是“未知”。
- 命令行与报告：终端、JSON、Markdown（贴进 PR 也不会渲染出链接、图片、@提及）；并发查询，每个站点各自限速。
- LaTeX 工程：跟着 \input / \include 找出正文真正引用了的文献（natbib、biblatex 的各种 \cite），注释和 \iffalse 里的不算；未定义的引用、没被引用的条目；参考文献可以来自 .bib、.bbl（BibTeX 各种样式和 biblatex）或 thebibliography。
- 论文自洽（离线，不发任何请求）：加粗却不是最好的数字、“从 A 到 B 提升 p%”重新算、摘要里的数字在正文和表格里都找不到、引用了不存在的标签、重复定义的标签、从未被提到的图表。
- 在 20 篇著名论文的 arXiv 源码上量误报：第一版 85 条警告，几乎全是误报（并列加粗、按类别加粗、模型在列里的转置表、人类/训练集参考行、放在宏和 \iftoggle 分支里的标签、宏参数 #1）。逐条看源码修正后剩 3 条，**3 条都是真的**：
  - LoRA（2106.09685）GLUE 表 QQP 列：加粗 91.9，同组 92.1 更高（标题写明“越高越好”）；
  - LLaVA（2304.08485）：标签 tab:full_example_car_bbox 在正文和附录各定义一次；
  - vLLM（2309.06180）：标签 eq:attention-layer 定义了两次，正文引用的其实是第二个公式。
- 扩到 50 篇（加了 Chinchilla、Flan、BLIP-2、SAM、Whisper、ControlNet、ReAct、QLoRA、Mistral、DINOv2、ConvNeXt、Swin 等 30 篇）再量：新出现的误报来自对角线加粗（ALiBi）、加粗表示“最大”而非“最好”（MT-Bench）、每组一行各自加粗（Mistral）、表头里的 \cmidrule、“ranging from 33% to 90%”这类区间、AUCTeX 的 _region_.tex 被当成主文件；逐个修正并写进测试。
  - 现在 50 篇共报 6 条错误/警告，**逐条对照源码全部属实**：上面 3 条，加上 DINOv2（2304.07193）数据消融表 ADE-20k 加粗 47.7、但 Uncurated data 是 48.5；BLIP-2（2301.12597）fig:example_limitation 两张图共用一个标签；LLaVA-1.5（2310.03744）两张表都叫 tab:results。
  - 没人引用的重复标签降为提示（Flan 附录里十张表都叫 tab:my-table，留着无害）。
  - 摘要数字、“从 A 到 B 提升 p%”两项在这 50 篇里没有报出问题：要么这些著名论文确实没写错，要么检出偏保守。下一步用人为注入的错误量检出率。
- 注入错误量检出率（scripts/inject_errors.py，在内存里改，不动源码）：
  - 第一次：把正确的加粗挪到更差的格子 27/35；改摘要里的数字 **1/11**。原因：摘要数字只要等于任意两格之差就放过，表一多几乎什么都能“凑出来”。改为：摘要在说“提升/高出/降低多少”时才允许是差值，并接受四舍五入（表里 28.43、摘要写 28.4）。
  - 表头下面没有横线的表（LDM 的 FID 表）被当成 7 行表头：改为表头下的横线出现得晚时，按“前面不含数字的行”定表头。
  - “Average human expert”“2023 forecast”这类参考行不参与比较（Chinchilla 的 MMLU 表）。
  - 标题里出现 significantly 不再一律跳过，只在标题同时说到加粗/高亮时才算“加粗另有含义”。
  - 最后：加粗 **41/42（98%）**，摘要数字 **9/11（82%）**；50 篇真实论文共 7 条错误/警告，**7 条全部属实**——新增一条：Chinchilla（2203.15556）摘要写 MMLU 67.5%，正文和表格都是 67.6%。
- 测量脚本和论文清单（只有 arXiv 号）放进 scripts/，源码不进仓库。

## 第 1 轮打磨（2026-11-13）

- **参考文献联网测量**（scripts/measure_refs.py，5 篇论文 264 条：Transformer、LoRA、DPO、LLaMA、Mistral）：第一次 23 条“信息不符”、5 条“查无此文”，逐条核对几乎都是误报。原因和修正：
  - 年份：引用年份比记录**晚**多半是后来的版本或重印（Adam 引 2017 的 arXiv v9，Luce 1959 年的书 2012 年重印）→ 改为提示；比记录**早**仍算错误。同名的会议版和期刊版（Bengio 2000/2003）按引用年份挑最接近的记录。
  - 姓名：复合姓与小品词（Ben-Zaken / Zaken、El Showk / El-Showk）、先姓后名（“Mostofa Ali Patwary”被引作 Ali）、ø/ł/ß 这类 NFKD 拆不开的字母（Søraker）；长作者列表里个别对不上只算提示（多半是拼写变体）；记录比引用的作者少时（书的章节、老论文）缺的人不算证据。
  - 标识符：arXiv 自己的 DOI（10.48550/arXiv.…）当 arXiv 号查；Crossref 没有的 DOI 再问 doi.org（Zenodo 等 DataCite 的 DOI）是否存在；有确切标识符时标题略有不同（arXiv 上改过标题）仍是同一篇。
  - 团体作者（BigScience Workshop）不比第一作者；标题只引了前半截（“A decomposable attention model”）时第一作者和年份对得上才算同一篇，并给出完整标题；第一作者对不上时继续查别的库（Shannon 1948 先匹配到一条 2006 年的同名记录）。
  - 修完用缓存重算：信息不符 23 → 4、查无此文 5 → 3。剩下的里两条是论文参考文献里真的错：LoRA 把 Jihun Hamm 写成 Ham；DPO 引 “Dueling RL” 时把 Saha 写成第一作者（实为 Aldo Pacchiano）。
- **PDF 路径**（scripts/measure_pdf.py，5 篇论文的 PDF 对照各自的 LaTeX 参考文献，372 条）：标题读对 204 → 323，整条能匹配到 367。修了：首字母后多出空格（“Y . Bai”）、“et al.” 结束作者列表、句点后缺空格（“time.arXiv”）、以问号结尾的标题、以编号或年份结尾的条目、“Title: subtitle”被误当成 LNCS 的“作者: 标题”。
- **HTTP**：重试用完的 429/5xx 以前会被当作普通应答返回（源头再判 unknown，结论没错但熔断计数不到），现在抛错；同一站点连续失败 3 次本次运行就不再问（Semantic Scholar 无 key 时常连续 429，原来每条都要等十几秒退避）。
- **CI**：Python 3.10 上 3 个 doctest 失败（示例写在文档字符串第一行，3.13 才会自动去缩进），已改；本地也用 3.10 跑一遍。
- **体验**：`--fail-on` 的帮助文字和实际行为对齐；README 补上 arXiv 号与 PDF 两种输入。
- 测试 96 个（录音重录，新增 arXiv DOI、Zenodo DOI、引用年份更晚三种情况）。代码审查子任务因额度用尽中断，额度恢复后继续。

## 第 2 轮打磨（2026-11-13，进行中）

- 社交预览图 docs/social-preview.png（scripts/social-card.html，无头 Chrome 渲染），终端内容是示例论文的真实输出（缩短）。
  示例论文里 Houlsby 的年份改成 2016：差一年在容忍范围内不报，原来写的 2018 演示不出“信息不符”。需要在仓库 Settings → Social preview 上传。
- 首次运行：按 README 用 `uvx --from git+https://github.com/zch6a/paper-proof` 在全新的 uv 缓存下安装并运行，约 17 秒（之后走缓存），示例论文输出正确。
- OpenAlex 不带 key 的每日额度今天已用完（一直 429）：熔断让这种情况下的运行不会变慢，结论落到“未知”或“其余数据库都没有”；README 已写明可设 `OPENALEX_API_KEY`。扩大参考文献测量改到额度恢复后。
- **独立代码审查**（子代理，只读、不联网，复现脚本在草稿区）找到 11 个问题，复现了 10 个，全部修好并各写一个回归测试（tests/test_review_regressions.py）：
  1. 重复条目并行查询时同时写同一个缓存临时文件，Windows 上 `os.replace` 抛 PermissionError 让整个运行崩溃 → 每次写用独立临时文件、写失败不影响检查、同一 URL 同一时间只请求一次。
  2. `IncompleteRead`（不是 OSError）和读错误正文时超时会逃出重试逻辑而崩溃 → 一并算“没有应答”。
  3. 只有 DOI 没有标题的条目被判“查无此文”→ 没有标题时以标识符查到的记录为准。
  4. “from A to B”正则里三个相邻的空白量词，公式被抹成空格后会出现长空白串：4000 字符要 64 秒（ReDoS）→ 重写成互不重叠，2 万个空格也在 1 秒内。
  5. 非 UTF-8 的 .bib 直接崩溃；工程里的则把 Müller 变成 M�ller 导致第一作者误报 → 依次尝试 UTF-8、cp1252、Latin-1。
  6. 截断的 arXiv 源码包抛 EOFError 崩溃 → 给出“源码包损坏”的错误信息。
  7. 解压炸弹：只限了压缩后的大小，300 KB 能解出 314 MB → 流式解压，总共超过 500 MB 就停。
  8. Windows 上 `\input{//host/share/x}` 会先对 UNC 路径做 resolve/is_file 再判断是否在工程内，会发起 SMB 连接（可能泄露 NTLM 哈希，查别人的 arXiv 论文时也会触发）→ 先按文本拒绝绝对路径、盘符、UNC 和跳出工程的路径，再碰文件系统。
  9. `\multicolumn{3000000}` 分配上百万个格子 → 上限 64。
  10. 缓存会存下“200 但不是答案”的页面（机器人验证页），30 天里都读回这个坏答案 → 只缓存合法的 JSON/XML。
  11. Markdown 报告里裸 URL 会被 GitHub 自动变成链接 → 用零宽空格打断 `://` 和 `www.`；顺带不再转义圆括号（方括号转义后它们渲染不出任何东西），报告更干净。
  - 另：action.yml 里路径参数前加 `--`，以 `-` 开头的路径不会被当成选项。
- 修完重新测量：50 篇论文的发现、注入错误的检出率与修之前完全一致。测试 110 个（3.10 / 3.13 都过）。

## 第 3 轮打磨（2026-11-13）

- **新检查：正文与表格**。指向某张表（`\ref{tab:...}`）的句子里写的小数，应在那张表里（允许四舍五入），或在说“提升多少”时是表中同一列/同一行两个数的差或相对变化。
  - 第一版在 50 篇真实论文上报 19 条，逐条看：句子里同时引用了别处的数字（ResNet 一句里混着另一张表的 14.4%）、描述性数字（Transformer “每步 1.0 秒”）、差值在同一行而不是同一列（ResNet 的 plain/ResNet 两列）。
  - 改为：同一行的差也算；论文任何一张表里有这个数就放过；**只在被引的表里有一个同精度、相差 5% 以内的数时才报**（过时或打错的结果总在正确值旁边），并说出那个数。现在 50 篇里 0 条。
  - 量检出：在引用表格的句子里把表中出现的数改动 0.3，18 处查出 14 处；漏的 4 处都是 0.01、0.005 这样的小数，改动 0.3 已远超 5%。
  - 开发中出过一次崩溃（Table 不能当字典键），测量脚本把崩溃打印成 CRASH，我筛结果时滤掉了，差点误判成“检查变保守”；已修，并在之后的测量里专门看 CRASH。
- 示例论文加一句“29.2 BLEU (Table~\ref{tab:main})”演示新检查，CI 断言也加上这一类；README 中英文输出块换成真实的新输出，功能表和准确度加上这一项。
- **新检查：平均值列**。“Avg / Average / Mean”列应是本行前面那些数的平均。诊断了 50 篇里 38 张带平均列的表：LoRA GLUE 表 14 行、FlashAttention LRA 表 9 行、Flan 两张表各 24 行全对；
  MMLU 的平均是按学科数加权的、ALBERT 的平均另有定义，大部分行对不上——这类表整张不报（只在多数行对得上、少数行对不上时报）。
  - 表头要整格是“平均”（“Avg doc len”“Mean Age”“Avg. # Turn”不是本行的平均）。
  - 第一版允许“最后几个数的平均”任取长度，行一长总能凑出来（Flan 两处注入没查出）→ 改为整张表投票选一个长度、每行都按它判。
  - 量检出：只在“平均列确实是简单平均”的表里注入（50 篇里只有 6 张），改动 0.5，6/6 查出；50 篇真实论文 0 误报。
- **GitHub 上的实际渲染**：用 GitHub 自己的 Markdown 渲染接口（`gh api markdown`，GFM）渲染报告，标题里放链接、裸 URL、`<img onerror>`、@提及、粗体、反引号、竖线：
  表格正常渲染，没有链接、图片、提及或 HTML（scripts/check_github_render.py 可复跑）。顺带修了“1 references”的单复数。
- **演示图** docs/demo.png（scripts/render_demo.py）：真实的彩色终端输出转成 HTML 再用无头 Chrome 渲染，不截屏幕；放在 README 顶部，文字版收进折叠块。
  - 做图时发现：环境里设了 NO_COLOR 时 FORCE_COLOR 不生效。改为显式的 FORCE_COLOR 优先，并加 `--color auto|always|never`（有测试）。

## 第 4 轮打磨（2026-11-13）

- **代码结构**：numbers.py 涨到 650 行，按检查拆成 paper_proof/checks/ 下六个模块（common、bold、changes、stale、labels、averages，各 80–150 行），numbers.py 只留 check_numbers 和对外的名字（测试和测量脚本照旧能用）。用脚本按 AST 搬运，不手抄；拆完 50 篇论文的发现与注入检出完全一致。
- **死代码**：删掉没用的 POINTS 正则、_numbers_in、表格单元的 underline 字段和 UNDERLINE 正则（下划线检查早已去掉）。
- **类型**：mypy 第一次跑出 26 处。其中真问题：`urllib.request.quote` 不是公开接口（改用 urllib.parse.quote）；arxiv_source.fetch 遇到非法编号会在 None 上取 group（改为明确的 ValueError）；bib.py 一个变量先当整数后当匹配对象。其余是 Optional：给 Cell 加了断言过的 `num` 属性，已知是数字的格子都用它。现在 mypy 零问题，加入 dev 依赖和 CI。
- **打包**：构建 wheel 确认新子包 checks/ 在里面（从 GitHub 安装不会缺模块）。
- **对照 README 逐条实测**（fail-on 三档、--jobs 0、错误的 --checks、不存在的文件、没有 .tex 的文件夹、未知后缀、损坏的 PDF、空 .bib、没有参考文献的 .tex、非法 arXiv 号），发现三处并修好、各加测试：
  1. 损坏的 PDF 直接抛 pypdf 的异常栈 → “cannot read this PDF (...)”，退出码 2。
  2. 离线模式下未定义的 `\cite` 不报——它本来就不需要联网 → 离线也报。
  3. 没有参考文献的 .tex 直接以退出码 2 结束，连数字检查都不做 → 照常做数字和标签检查，并加一条提示“没找到参考文献，引用没有检查”（这时也不把每个 `\cite` 都算成未定义）。
- **文档**：CONTRIBUTING 加上源码结构表；README 离线输出块按新的说明文字重新生成。测试 116 个。

## 第 5 轮打磨（2026-11-13）

- **扩大测量没做成**：OpenAlex 不带 key 的额度仍是 429（这一天的测量用完了）。留给下一个循环：参考文献再加 5 篇、PDF 再加 5 篇。
- **文档与行为逐条对照**：README / 中文 README / SECURITY 补上 doi.org（Crossref 没有的 DOI 到那里确认存在）、新的年份规则（早一年以上是错误，晚的只是提示）、
  连续失败的数据库本次不再问、给 arXiv 号时即使 `--offline` 也会取源码。CHANGELOG 补上新检查的检出率、参考文献测量和代码审查的加固。
- **发布 v0.1.0**：Action 示例改用 `@v0`；打 tag v0.1.0 推送，release 工作流（只读任务里测试、构建、取 CHANGELOG 小节；写权限任务只调 gh）建 GitHub Release 并把 v0 标签指过去。不发 PyPI。

### 2026-11-14 — a link to research-kit

Both READMEs now end (before the licence) with a short section pointing to research-kit, the toolkit's front door: all
thirteen tools in the order of the work, and one Claude Code plugin marketplace for their skills. Documentation only.

### 2026-11-14 — the release workflow and plain tags

The release workflow moves the major tag (v0) to the released commit. For a plain (lightweight) tag it asked GitHub
for a tag object at the commit's sha; that request fails, gh prints the error body on stdout, and the `|| echo` kept
that text in front of the sha, so v0 would not have moved. It now reads the ref's type and follows a tag object only
for an annotated tag, and stops if what it got is not a sha (the same fix arxiv-diff had in its final review).
Releases so far used annotated tags and were not affected.

### 2026-11-14 — 0.2.0: whole-paper consistency, and a review mode

Chosen from research-kit's list of needs nothing covers: checks across a whole paper (LanguageTool, Vale and
TeXtidote read one sentence at a time), and help for reviewers that runs locally (review generators write whole
reviews, which most venues forbid, and call hosted models).

**Consistency** (`checks/consistency.py`): acronyms (two expansions, spelled out again, used before, only in the
abstract or a caption), one term written two ways, British and American spelling mixed, a symbol given two meanings.
Prose first: math, `\cite`/`\ref`/`\label`/URL arguments and command names blanked, line breaks kept. Reading order
follows `\input`, so a definition in an included file counts where it is read.

**Measured on the 50 arXiv sources** (fetched to a temporary folder, deleted after), every finding of the rarer kinds
read and the frequent ones sampled:
- first run: 7 "two expansions", 3 of them false (LaTeX's closing quotes '' counted as part of the last word); fixed:
  5 left, all real (Mamba's SSM as "structured state space models" and "state space sequence models"; RoFormer's
  RoPE as "Rotary Position Embedding" and "rotary position encoding"; InstructGPT's RM; BERT's MLM; Mamba's LTI, a
  change of word form only);
- "ground truth" against "ground-truth", "trade off" against "trade-off" were reported: noun and adjective, noun and
  verb. Now only pairs where one form is closed up are reported; 28 of 30 sampled are then real;
- British and American mixed: 11 papers, all real (CLIP, GPT-3, DINOv2, Llama 2, ...); "analyses" (a plural) and
  "laboratory" (not "labor") are no longer evidence;
- the matcher read "state space sequence models (SSMs)" from the S of "sequence"; the quoted expansion now takes the
  word before with the same initial ("state"), and two expansions are the same when one ends with the other.
- symbols: 128 definitions found, none with two meanings; tested on made-up text.

**PDF**: the text with pages kept (form feeds), the reference list blanked (its heading was missed at the top of a
page: fixed), the abstract found between "Abstract" and "Introduction". Claimed changes and abstract numbers are
checked on it, with page numbers. On five arXiv PDFs (LoRA, Mamba, RoFormer, Tree of Thoughts, BERT) the same real
acronym findings appear as from the sources. Two wrong turns fixed on the way: BERT's "7.7% point absolute
improvement" was taken for a stale number (the clause after a number is now read), and then "41.2 accuracy, 3.1
points over the baseline" hid 41.2 (only the number's own clause counts). "Low-Rank Adaptation, or LoRA" is now a
definition (LoRA's paper writes it so).

**`--review`**: nothing sent (no reference lookups unless `--lookup-references`), the report starts by saying what was
sent and that each point is something to check, exit code 0. The Agent Skill says to use it for someone else's
submission and never to write the review.

16 tests (133 in all, on Python 3.10 too); README, Chinese README, Action input and Skill updated; the example paper
has two consistency slips (an acronym spelled out only in the abstract, "pretrained" next to "pre-trained").
