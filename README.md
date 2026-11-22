# 每日简报 / Daily Brief

每天早上（美东 6–7 点）自动做一份中美热点简报：

- **抓取**：抖音、微博、知乎、B站热榜，X 美国趋势，21 个 YouTube 新闻频道的新视频，以及按话题搜的 Google News（中文区和美国区各一次）。
- **整理**：DeepSeek 按你的话题挑出重要的事，把同一件事在不同平台、不同语言的报道合并成一条，用中英文各写一两句话，附上主要来源链接。
- **发布**：生成网页（右上角「中 / EN」一键切换），推一张卡片到飞书群，手机就会收到。

整个过程在 GitHub 上免费运行，电脑关机也照常更新。

---

## 第一次设置（大约 10 分钟）

### 1. 准备飞书机器人
1. 打开飞书**电脑版**，新建一个群（如果不让只有自己一个人，就把你的第二个账号拉进来）。
2. 群设置 → 群机器人 → 添加机器人 → **自定义机器人**，名字随便取，比如「每日简报」。
3. 安全设置里勾选**签名校验**，复制显示的**密钥**。
4. 复制 **webhook 地址**（`https://open.feishu.cn/open-apis/bot/v2/hook/...`）。

### 2. 准备 DeepSeek key
在 [platform.deepseek.com](https://platform.deepseek.com/api_keys) 创建一个 API key，账户里有几块钱余额就够用很久（每月大约 1 美元）。

### 3. 运行设置脚本
在项目文件夹打开 PowerShell，运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-github.ps1
```

它会依次：登录 GitHub（会打开浏览器）→ 建公开仓库 `daily-brief` 并上传 → 打开网站 → 让你粘贴三个密钥（DeepSeek key、飞书 webhook 地址、飞书签名密钥；粘贴时屏幕上不显示）→ 立刻生成一次。

大约 3 分钟后，网站出现在 `https://<你的GitHub用户名>.github.io/daily-brief/`，飞书群里也会收到卡片。

> 密钥只存在 GitHub Secrets 里，不会出现在代码里，也不要发到聊天里。

---

## 日常怎么改

所有设置都在 `config/` 文件夹，可以直接在 GitHub 网页上点文件 → 铅笔图标修改 → Commit，第二天生效。

| 想改什么 | 改哪里 |
|---|---|
| 增删话题 | `config/topics.yaml`（文件里有现成例子） |
| 开关某个平台、改抓多少条 | `config/sources.yaml` |
| 加减 YouTube 频道 | `config/sources.yaml` 的 `youtube.channels` |
| 每个话题几条、必知几条、飞书卡片显示几条 | `config/settings.yaml` 的 `digest` |
| 换 AI 模型（Claude、Gemini 等） | `config/settings.yaml` 的 `llm`，再把新 key 存进 GitHub Secrets |
| 换成自己的域名 | `config/settings.yaml` 的 `site.url`，再在 GitHub 仓库 Settings → Pages 绑定域名 |
| 生成时间 | `.github/workflows/daily.yml` 的 `cron`（UTC 时间）和 `settings.yaml` 的 `run_after_hour` |

**马上重新生成一次**：GitHub 仓库 → Actions → daily-brief → Run workflow（勾上「重新生成今天的日报」）。
**只测试飞书**：同一个地方勾「只把最新一期推送到飞书」，不会调用 AI。

**网页上选话题**：点顶部的话题标签就能隐藏/显示，会记住你的选择。

---

## 本地运行（备用）

云端出问题时，可以在本机跑：

1. 把 `.env.example` 复制成 `.env`，填上 key。
2. 运行 `powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1`，完成后会自动打开网页。

想让本机每天 7 点自动跑（错过就开机补跑）：`scripts\install-local-task.ps1`。云端和本地只开一个，否则会收到两份推送。

其他命令：

```text
python run.py --fetch-only    只测试抓取，看每个来源抓到几条
python run.py --force         重新生成今天的
python run.py --no-push       不推送飞书
python run.py --push-latest   把最新一期再推送一次
python run.py --render-only   只重新生成网页
```

---

## 已知限制

- **X**：只有美国趋势榜（来自 trends24.in）。看具体博主的帖子需要付费的 X API（按条计费，每天约 100 条大约每月 15 美元），暂未开启。
- **小红书、Reddit**：前者必须登录才能抓，后者封锁程序访问，所以没加。
- **热榜接口都不是官方的**：哪天某个平台改了接口，那一栏当天会空着，网页底部会写「今天没抓到：…」，其他部分照常。
- **Google News 链接**会尽量还原成原文地址；还原不了的保留 Google 的跳转链接，点开一样会转到原文。
- **GitHub 的定时会晚 10–30 分钟**，偶尔整次跳过；工作流设了补跑。
- **网站是公开的**，任何知道网址的人都能看。

## 思路参考

- [Thysrael/Horizon](https://github.com/Thysrael/Horizon)（MIT）：AI 打分、同一事件去重、中英文输出、GitHub Pages 发布的思路。
- [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar)：中国热榜聚合与推送。
- [newsnow](https://github.com/ourongxing/newsnow)：微博等热榜通过它的公开接口获取。

本项目代码为独立编写，没有复制以上项目的代码。
