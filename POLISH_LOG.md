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
