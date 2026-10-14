# Kelip · 论文精读（GitHub：kelip-paper-reading-web）

ChatGPT 网页端论文精读 Skill，由 [skJack/kelip-paper-reading](https://github.com/skJack/kelip-paper-reading)（MIT）适配。保留六站精读、原图检查、样本/张量解释和只读代码核对，新增离线 HTML、可恢复 ZIP、Google Drive 与原生 Google Sheets 索引。

## 显式调用（v0.2.4）

**默认不自动启动。** 首次进入 Kelip 工作流必须在用户消息中明确说“用 Kelip ...”“调用 Kelip ...”，或在 ChatGPT 的 Skill 选择器里主动选择 Kelip。仅发论文链接、上传 PDF、让 GPT 讲解/总结/比较论文，均走普通 ChatGPT，不触发六阶段脚本或 Drive 归档。

原完整名称 `kelip-paper-reading-web` 仍可作为**明确调用时的旧别名**。在同一对话中已开启 Kelip 并阅读同一篇论文后，“继续”“解释这个公式”“归档”可沿用当前阅读状态而不用重复点名。新的论文需要重新明确调用。

**重要：名称改为 `kelip` 后，安装时可能被识别为一项新 Skill。请移除或停用旧版 `kelip-paper-reading-web`，避免旧版宽泛描述继续自动触发。** 通过 Skill 名称和描述做路由属于模型判断，不是产品级的强制手动开关；需要用新对话检查误触发。

## 安装

下载已构建的 **kelip-paper-reading-web-0.2.4.zip**，在你已有的 Plugins / Skills 本地上传入口安装。包内只有一个 Skill 文件夹，顶层包含 SKILL.md。以平台实际安全扫描结果为准；源码 ZIP 不是带依赖的安装包。

无需在自己的电脑安装 Python、搭服务器或申请 Google API 密钥。脚本由 ChatGPT 的实际执行环境运行，云端操作使用已连接的 Google Drive。安装 Skill 不会自动授予新服务权限。

需要支持自定义 Skill 的账户、Python 执行环境及 PyMuPDF。安装包附带 Markdown/MathML 的纯 Python 辅助库和许可证，不附带字体。仓库源码自行构建：

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/build_skill.py --out dist
```

GitHub Actions 自动测试并产出安装包、源码包和测试日志，可在本仓库 Actions 的成功运行中取得。

## 用法

```text
用 Kelip 精读 <arXiv 链接>，先讲动机。
# 以下在已经启动的同一篇论文对话中使用
直接讲数据：一条训练样本是什么样？
这篇先到这里，把笔记和问答归档到 Google Drive。
继续读 arXiv:2410.24164，上次讲到哪里？
恢复这个 ZIP，再继续训练部分。
补充刚才的问题，保存为新版本。
```

默认一站一站讲，可打断和跳站。结束或暂停时询问一次是否归档；已经明确要求保存就直接执行，不每轮自动上传。部分完成也可保存。

## 图像展示与编号验证（v0.2.2）
增加 references/figure-delivery.md 与 scripts/prepare_figure.py：论文 Figure 必须先显示原始图像，再讲内容。脚本从 figures/index.json 定位 PNG，自动裁剪不准时支持 PDF 页预览和手动坐标重裁。
新版绑定图片、原始 PDF 页和准确 Figure caption，采用 PDF 重渲染而非来源不明的网页首图或缓存 PNG；无法核对时不再冒名展示。

引用链接、路径或图注不能当作图片已经发送。若平台当前没有用户可见的图像输出工具，必须明确告知未内嵌图片并提供已验证图片附件。prepared != displayed。

## 默认无负担精读和旁支提问（v0.2.3）

用户明确调用 Kelip 后，只需提供 arXiv 链接或 PDF。Skill 自己根据章节挑选相关原图、核对 PDF 图号/图注/页码/视觉内容，正确后展示；不要求用户指定 Figure 编号或提供配图审核要求。临时插问不推进六阶段阅读，用户说“继续”后接着原阅读位置。普通网页版尚无由 Skill 自建的独立侧边问答 UI；分支聊天与本会话问答并非自动同步。

## 存储

```text
PaperReading/
├── PaperIndex  [原生 Sheet：Papers / Versions / Settings]
└── papers/
    └── YYYY/   [首次归档年份]
        ├── <storage-key>__report.html
        ├── <storage-key>__r0001__<archive-short-id>.zip
        └── <storage-key>__r0002__<archive-short-id>.zip
```

HTML 更新同一 Drive ID；ZIP 不覆盖，按报告版本和唯一归档 ID 保存。上传后回读校验 SHA-256，再更新索引；重试复用已成功的文件。arXiv/DOI 精确查找，标题相似不自动合并。稳定 paper_id、作者论文版本、阅读报告版本、Drive 修订分别管理。

ZIP 保存报告、问答、阅读位置、已取得 PDF/LaTeX/图表/代码及校验清单。缺失资料在 manifest 中明示。它不包含权重、完整数据集、凭据或运行中 Python 状态。

**Drive 不是 HTML 网站托管。** 返回的是私人文件访问链接；HTML 下载后可离线阅读、搜索问答和展开内容。没有 Drive 连接仍能本地打包。没有 PDF 字节不假装已执行本地解析。

## 代码结构

- SKILL.md：网页端阅读与归档入口。
- references/：原版讲解样例/笔记模板，以及运行时和归档协议。
- fetch_paper.py：真正的 --offline 入口；保留 upstream_fetch_paper.py 原版实现并适配边界。
- extract_figures.py / crop.py：保留原版裁图工具。
- prepare_figure.py：检查自动裁图并输出可发送的真实 PNG；最终仍须通过图片展示工具呈现。
- paper_identity.py：标识规范化与身份保持。
- render_report.py：图像内嵌、MathML、自包含 HTML 和问答交互。
- reading_bundle.py：初始化、构建、校验、安全恢复。
- cloud_index.py：上传回读校验、幂等索引更新请求；不含网络/OAuth。
- build_skill.py：打包并附带必要纯 Python 库及其许可证。
- tests/：身份、离线输入、恢复、版本链、篡改/路径攻击、报告、索引/重试测试。

实际云端读写由 Skill 调用连接器，不是脚本自动访问 Google。请求计划不等于写入成功，必须执行并回读。

## 已知边界

裁图仍需视觉检查；复杂公式失败时给警告，应改用原式裁图。临时磁盘不保证跨会话保留。Drive+Sheets 不是跨服务事务；本版按每篇论文单写入者设计，检测已观察到的冲突，不提供分布式锁。安装扫描、真实论文阅读质量和各账户工具可用性仍需实际安装后验证。

个人画像、Drive ID、阅读记录、测试成果和凭据不应提交到公开仓库。

## License

MIT；保留原作者 LICENSE。打包引入的辅助库保留各自许可证。
