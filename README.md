# 每日简报 / Daily Brief

每天早上（默认美东 7 点后）自动做一份中美热点简报：

- **抓取**：抖音、微博、知乎、B站热榜，X 美国趋势，21 个 YouTube 新闻频道的新视频，按话题搜的 Google News（中文区和美国区各一次），以及 GitHub 今日热门项目、本周新项目和热门 agent skill（skills.sh）。
- **整理**：DeepSeek 按你的话题挑出重要的事，把同一件事在不同平台、不同语言的报道合并成一条，用中英文各写一两句话，附上主要来源链接；GitHub 项目各写一句「这是做什么的」。
- **发布**：生成网页（右上角「中 / EN」一键切换），推一张卡片到飞书群，手机就会收到。

整个过程在 GitHub 的服务器上免费运行，**电脑关机也照常更新**。

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

## 设置页（改功能和偏好）

日报网页右上角的齿轮（或页面最底下的「设置」链接）打开设置页，手机上也能用：

- **话题**：每个话题开/关；添加新话题（填中英文名和关键词就行）
- **信息来源**：抖音、微博、知乎、B站、X、YouTube、Google News、GitHub 各自开/关
- **篇幅**：每个话题几条、必知几条、飞书卡片几条、GitHub 三个列表各几个
- **推送**：每天几点后推送（美东时间）、飞书推送开/关、网页默认语言
- **马上执行**：现在重新生成今天的日报、测试飞书推送

改完点底部「保存设置」，下一次生成时生效。

**第一次用要连接 GitHub**（因为保存其实是往仓库里改 `config/preferences.json`）。设置页上有步骤，简单说就是：
1. 打开 [GitHub 新建 token 页面](https://github.com/settings/personal-access-tokens/new)
2. Repository access 选 **Only select repositories** → `daily-brief`
3. Permissions 里 **Contents** 和 **Actions** 都选 **Read and write**
4. 生成后复制，粘到设置页点「连接」

token 只存在那台设备的浏览器里，只发给 GitHub；换手机或清了浏览器数据要重新粘一次。不想用了，在设置页点「断开」，再到 GitHub 上删掉这个 token。

**网页顶部的话题标签**只是在你这台设备上临时隐藏某个栏目，不影响生成。

### 更细的设置（改文件）

在 GitHub 网页上点文件 → 铅笔图标修改 → Commit，下一次生成时生效。

| 想改什么 | 改哪里 |
|---|---|
| 话题给 AI 的说明、搜索词 | `config/topics.yaml` |
| 每个源抓多少条、YouTube 频道 | `config/sources.yaml` |
| 换 AI 模型（任何 OpenAI 兼容接口） | `config/settings.yaml` 的 `llm`，再把新 key 存进 GitHub Secrets |
| 换成自己的域名 | `config/settings.yaml` 的 `site.url`，再在 GitHub 仓库 Settings → Pages 绑定域名 |

### 换 DeepSeek key

```powershell
powershell -ExecutionPolicy Bypass -File scripts\set-deepseek-key.ps1
```

它会先拿 key 去问 DeepSeek，有效才存进 GitHub，然后马上重新生成一次。

---

## 什么时候运行

GitHub 每小时叫醒一次程序（它的定时经常晚几个小时，所以不靠准点）。程序自己看：到没到设置里的推送时间、今天做过没有；没到或做过就几秒钟结束。所以日报一般在推送时间后 1 小时内到。GitHub 的 Actions 页面里每天会有二十几条「跳过」的记录，正常。

**AI 出错时**（key 失效、余额不够、接口故障）：照样发一份「无 AI 版」——新闻原标题、热搜、GitHub 列表都有，只是没有摘要；网页和飞书卡片（变成橙色）顶上写着哪里出了错。之后每小时会再试一次 AI，成功了就换成正常版并重新推送。

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
- **GitHub 的定时会晚，有时晚好几个小时**；所以改成了每小时检查一次。
- **网站是公开的**，任何知道网址的人都能看（设置页也能打开，但没有你的 token 改不了任何东西）。
- **GitHub 本周新项目**按总星数排，偶尔会混进刷星的项目。

## 思路参考

- [Thysrael/Horizon](https://github.com/Thysrael/Horizon)（MIT）：AI 打分、同一事件去重、中英文输出、GitHub Pages 发布的思路。
- [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar)：中国热榜聚合与推送。
- [newsnow](https://github.com/ourongxing/newsnow)：微博等热榜通过它的公开接口获取。

本项目代码为独立编写，没有复制以上项目的代码。
