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
