# 部署到个人微信

## 1. 准备 Server酱

1. 打开 [Server酱](https://sct.ftqq.com/) 并登录。
2. 按 Server酱页面指引完成个人微信接收通道绑定。
3. 在 Server酱后台复制 SendKey。不要把它写入代码、Issue、聊天截图或 `.env.example`。

本项目只调用 Server酱推送 API，不会登录个人微信。

## 2. 创建 GitHub 仓库配置

建议将仓库设为私有。进入仓库：

`Settings → Secrets and variables → Actions`

添加 Repository Secret：

- `SERVERCHAN_SENDKEY`：必填，Server酱提供的 SendKey。
- `SUMMARY_API_KEY`：仅接入自选摘要服务时需要。默认使用 GitHub Models 自动将项目简介转为简体中文，由工作流的 `GITHUB_TOKEN` 授权。

默认摘要服务没有返回可用结果时，工作流可通过 MyMemory 翻译公开的 GitHub 仓库简介。译文缺失时，微信消息会提示打开仓库查看原文。

可选 Repository Variable：

- 配置 `SUMMARY_API_KEY` 后，可用 `SUMMARY_API_BASE` 和 `SUMMARY_MODEL` 指定兼容接口及模型，默认值为 `https://api.openai.com/v1` 和 `gpt-4o-mini`。

GitHub Actions 会自动提供 `GITHUB_TOKEN`，无需手工创建。

## 3. 本地安装与预览

需要 Python 3.12：

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
github-trending-wechat preview
```

不指定日期时，预览实时滚动榜。指定日期时，预览该日期的已归档快照：

```bash
github-trending-wechat preview --date 2026-11-24
```

预览默认不写入 `data/`。需要采集并保存当日快照时，可以运行：

```bash
github-trending-wechat capture
```

## 4. 验证微信绑定

在 GitHub 仓库进入 `Actions → Daily GitHub Trending to WeChat → Run workflow`：

1. `mode` 选择 `test-binding`。
2. `environment_label` 填 `github-actions` 或自定义环境名称。
3. 运行并等待个人微信收到“绑定测试”消息。

本地也可以执行：

```bash
github-trending-wechat test-binding --environment local
```

若返回认证失败，请更新 `SERVERCHAN_SENDKEY`；认证错误不会自动重试。

## 5. 首次正式发送

在同一工作流中将 `mode` 选择为 `run`。留空 `target_date` 会发送北京时间前一日的归档快照。想立即验证新部署，可先运行 `capture`，然后用 `run` 并填入北京时间当天日期。

本地正式发送命令：

```bash
github-trending-wechat run
```

成功后应同时看到：

- 个人微信收到 GitHub 热榜消息；
- `data/digests/YYYY-MM-DD.json` 保存不含秘密的榜单快照；
- `data/deliveries/YYYY-MM-DD.json` 保存榜期、执行结果和去重所需的接收配置指纹。服务方消息标识与原始错误文本不写入归档。

同一榜期已向同一个接收配置成功发送后，普通运行会显示 `idempotent_skip`。需要再发送时使用 `resend`。

## 6. 每日自动执行

启用 Actions Variable `DAILY_DIGEST_ENABLED=true` 后，工作流按北京时间在 23:55、08:00 和每小时第 17 分钟触发，以实际启动时间决定操作。

- 23:55 至次日 02:55 前采集，归入 23:55 所在的榜期。已有快照时直接复用。
- 08:00 至 23:55 前尝试发送前一日的榜单。发送成功后，同一接收配置的后续触发自动跳过。
- 缺少本站快照时，尝试读取 [GitHub Trending Archive](https://github.com/antonkomarev/github-trending-archive) 中同日全语言归档。消息会标明上游归档提交时间和来源，历史 Star 数留空。历史归档也不可用时，运行记录会给出失败原因，下一次触发可以继续尝试。

GitHub Actions 可能延迟或跳过计划触发，实际推送时间以运行记录为准。

## 7. 补发

GitHub Actions 手动运行时：

1. `mode` 选择 `resend`；
2. `target_date` 必须填写 `YYYY-MM-DD`；
3. 确认消息标题包含“补发”。

本地命令：

```bash
github-trending-wechat resend --date 2026-11-24
```

`resend` 使用指定日期的本地快照，并保存新的发送记录。缺少该日快照时可以选择 `recover`，填写 `target_date`，用第三方同日归档补齐并按普通发送规则去重。

## 8. 停用与回滚

- 临时停用定时推送：将 `DAILY_DIGEST_ENABLED` 设为 `false`，仍可手动运行工作流。
- 永久停用：删除工作流并在 Server酱后台吊销 SendKey。
- 密钥轮换：更新 `SERVERCHAN_SENDKEY` 后重新运行 `test-binding`。
- 历史 JSON 不含完整密钥，可保留审计；如不希望保留订阅历史，可按仓库策略清理 `data/`。

