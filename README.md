# 华都 · 每日行业新闻海报 —— 云端部署包

电脑关机也能每天自动生成海报并推送到手机。

## 整体架构

```
GitHub Actions（每天北京时间 07:30 定时触发，免费）
  ├─ scripts/collect_news.py  → 抓取当日行业新闻（Bing 新闻 RSS 多关键词检索）
  │                            → 配置了大模型 Key 时自动精选润色，未配置则关键词加权筛选
  ├─ scripts/gen_poster.py    → 用与本地版完全一致的版式生成海报（字体已打包进仓库）
  ├─ docs/latest.png          → 固定网页链接（GitHub Pages），手机收藏随时看最新一期
  └─ 微信推送（可选）          → 通过 Server酱 推到你微信，点开就是海报
```

## 部署步骤（一次性，约 10 分钟）

### 1. 创建 GitHub 仓库
- 注册/登录 [github.com](https://github.com)
- 右上角 **+** → **New repository**
- 名称随意，如 `huadu-daily-poster`；可见性选 **Public**（免费账号开 Pages 需要 Public；海报是宣传内容，公开无妨）
- 不要勾选 README 初始化，点 **Create repository**

### 2. 上传本部署包的全部内容（作为仓库根目录）
网页上传最简单：仓库页 → **uploading an existing file** → 把本文件夹内的**所有内容**
（含 `.github` 隐藏文件夹——注意资源管理器里要打开「显示隐藏项目」）拖进去 → **Commit changes**。

> 注意：上传的是本文件夹**里面的内容**作为仓库根目录，不是把「云端部署包」文件夹本身传上去。

### 3. 开启 GitHub Pages（固定链接）
- 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
- 之后每次生成，固定链接即为：
  `https://<你的用户名>.github.io/huadu-daily-poster/latest.png`

### 4.（可选但推荐）微信推送
- 打开 [sct.ftqq.com](https://sct.ftqq.com)，微信扫码登录，免费获得一个 **SendKey**
- 仓库 **Settings → Secrets and variables → Actions → New repository secret**
  - Name：`SENDKEY`，Value：粘贴 SendKey
- 之后每天海报生成完，你微信会收到推送，点开就是海报图

### 5.（可选）大模型精选，新闻质量与本地版一致
- 注册 [platform.deepseek.com](https://platform.deepseek.com)，充几块钱，创建 API Key
- 加 Secret：`DEEPSEEK_API_KEY` = 你的 Key
- 不配置也能跑（走关键词筛选兜底），配置后标题和摘要质量更好

### 6. 验证
- 仓库 **Actions** 页 → 左侧「每日行业新闻海报」→ **Run workflow** → 运行
- 绿勾后打开固定链接看海报，微信查收推送

## 说明

- **GitHub 定时任务有 ±15 分钟左右的浮动**，海报一般在 7:30 前后生成，属正常现象
- 新闻抓取失败的兜底：脚本内置默认新闻数据，海报版式永不中断
- 每天的海报同时归档在仓库 `docs/` 目录，按日期命名，随时回看历史
- 微软雅黑字体文件随私有内容打包在 `fonts/`，仅供华都内部使用，请勿公开分发字体文件
- 电脑上的本地 WorkBuddy 自动化可以保留或停用，互不影响
