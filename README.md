# AI Frontier Radar | AI 前沿雷达

一份不需要安装 Node.js 的中文版 AI 情报网页。优先追踪 **AI 应用创新**，将 **基础技术** 和 **AI 基础设施** 作为辅助线索。

## 先看页面

直接双击 `site/index.html` 即可看到页面和经过来源核验的**示例快照**。页面顶部会标示「演示数据」，不会假装在实时更新。浏览器里可以搜索、分类、收藏，并点击每条动态查看中文导读和原文链接。

也可以运行本地 HTTP 服务器：

```bash
cd site
python -m http.server 8000
# 浏览 http://localhost:8000
```

## 部署成永久网址（推荐 GitHub Pages）

1. 登录 GitHub，创建一个**公开**仓库，例如 `ai-frontier-radar`。
2. 将本文件夹里所有文件和目录完整上传到仓库**根目录**（不要丢失 `.github/workflows/publish.yml`）。也可以在 GitHub 网页的 `Add file → Upload files` 上传（部分隐藏目录的上传需要通过仓库内新建文件的方式实现）。
3. 在仓库 `Settings → Pages → Build and deployment → Source` 选择 **GitHub Actions**。
4. 在 `Actions` 选项卡运行 `Refresh and publish AI Frontier Radar` 的 `Run workflow`（如果没有自动运行）。
5. 部署成功后访问 `https://你的GitHub用户名.github.io/ai-frontier-radar/`。实际网址以 Actions 的部署结果为准。

任务会**尝试每 4 小时**自动重新抓取 RSS 和 Hugging Face 论文数据，重新生成网站。GitHub Actions 计划任务可能延迟/中断，源站可能限流；这不是实时推送，也不是零延迟新闻。GitHub 的公开仓库计划任务还可能因长期无活动而自动暂停。网页不会在没有服务器的情况下自行抓取跨站 RSS。

## 想要 AI 自动写中文解读（可选）

不用配置 AI 密钥也能持续采集新标题、链接、分类，但英文原文标题会保持英文，自动生成的中文说明仅为**通用领域提示，不是文章内容翻译**。页面会如实标注其限制。

如果需要按文章生成中文标题、通俗导读和应用场景：

1. 在 GitHub 仓库 `Settings → Secrets and variables → Actions` 下创建 **Repository secret**，名称设为 `OPENAI_API_KEY`，填入你自己的 OpenAI API 密钥。
2. 如有需要，可添加 **Repository variable** `OPENAI_MODEL` 以指定拥有 Chat Completions JSON mode 能力的模型。默认 `gpt-4.1-mini`。
3. 在 Actions 中手动运行一次刷新，以生成中文摘要。

**API 密钥仅由 GitHub Actions 的 Python 后台读取，绝不可粘贴在 HTML、data.json 或公开仓库里。** API 调用可能收费；每次计划刷新最多对 24 条新采集结果进行一次批量生成，可能重复处理相同的新闻。请在 API 控制台设置预算上限和使用提醒。GitHub Pages 本身不提供后台 API。

## 默认数据来源

- OpenAI News (RSS)
- Google DeepMind (RSS)
- Google Research (RSS)
- Hugging Face Blog (RSS)
- MIT Technology Review — AI (RSS)
- TechCrunch — AI (RSS)
- NVIDIA Blog (RSS)
- AWS Machine Learning Blog (RSS)
- arXiv AI (RSS)
- Hugging Face Daily Papers (API)

各源条目只保存文章标题、少量元数据和原文链接；不存储全文。定时任务失败时保留可显示的经过核验的示例内容（若尚未过期）并给出错误日志。新闻源可能有版权、再发布或流量使用约束，网站只应供个人阅读使用；公开商业发行前应进一步核实各媒体条款。

## 局限

- 当前排序属于启发式分数，**不是经过专家逐条审定的全球技术排名**。
- 文章归类基于关键词，可能把基础研究误判为应用。
- AI 生成的摘要可能出错，请回到原文核实重要细节。论文预印本不代表同行评审通过。
- 这是网页和自动更新脚本，不包含消息推送、邮箱订阅、登录账户或者监控告警服务。
- 海洋照片由 Unsplash 提供，在线加载；断网时使用渐变海蓝背景。
