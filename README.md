# GitHub 热榜微信日报

每天北京时间 **23:55** 保存 GitHub Trending 日榜前十，次日 **08:00** 通过 Server 酱把中文日报发到个人微信。用 GitHub Actions 调度，无需常驻服务器。

每个项目包含仓库链接、简体中文简介、主要语言、总 Star 数和日榜新增 Star。默认按 GitHub Trending 的原始顺序呈现。榜单是抓取时的滚动日榜快照，日报会标明实际抓取时间和统计口径。

## 快速开始

1. Fork 本仓库，在 [Server 酱 Turbo](https://sct.ftqq.com/) 用微信扫码登录，确认默认通道，然后复制以 `SCT` 开头的 SendKey。
2. 在你的仓库打开 **Settings → Secrets and variables → Actions → Secrets**，新建 `SERVERCHAN_SENDKEY`，填入 SendKey。
3. 在 **Actions → Daily GitHub Trending to WeChat** 启用工作流。用 `test-binding` 确认微信收到测试消息。想立即试发日报时，先用 `capture` 保存当日榜单，再用 `run` 并填写当日的 `target_date`。也可以用 `preview` 在 Actions 日志里查看榜单。
4. 在同一设置页的 **Variables** 中创建 `DAILY_DIGEST_ENABLED`，值设为 `true`，开启每日推送。GitHub Actions 的计划任务可能稍有延迟。

工作流会把快照与发送状态归档到 `data/`。如果希望这些记录只对自己可见，可以在私有仓库部署。详见 [部署说明](docs/deployment.md) 和 [安全说明](docs/security.md)。

## 中文简介

已有中文简介直接保留。Actions 默认使用 GitHub Models，服务不可用时可通过 MyMemory 翻译公开的仓库简介。缺少可用译文时，日报会提示打开仓库查看原文。也可以配置自己的 OpenAI 兼容服务。

## 本地预览

需要 Python 3.12 或更高版本。预览无需配置 Server 酱密钥。

```bash
python -m pip install -e .
github-trending-wechat preview
```

本地配置摘要服务后也可以预览中文简介。其他命令和环境变量见 [部署说明](docs/deployment.md) 与 [.env.example](.env.example)。

## 许可证

[MIT](LICENSE)
