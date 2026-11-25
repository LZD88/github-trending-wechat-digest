# 安全说明

## 微信接入边界

本项目不会登录或控制个人微信，也不会索取微信号、微信密码、验证码或客户端会话。消息通过用户主动绑定的 Server酱服务发送，程序只需要 Server酱生成的 SendKey。

## Secrets 管理

- `SERVERCHAN_SENDKEY` 和 `SUMMARY_API_KEY` 必须配置为 GitHub Actions **Secret**，不得配置为普通 Variable。
- `GITHUB_TOKEN` 在 Actions 中使用平台自动提供的短期令牌；本地可选配置个人令牌，但不得提交到仓库。
- `SUMMARY_API_BASE`、`SUMMARY_MODEL` 可以配置为 Actions Variable，因为它们本身不是凭据。
- `.env` 已被 Git 忽略，`.env.example` 只包含占位符。
- 日志会遮盖 SendKey、Authorization、API Key 和 Token 形式的值。
- `data/` 仅保存公开榜单信息、不可逆接收配置指纹和脱敏错误，不保存完整密钥。

## 仓库可见性

榜单本身来自公开数据，但历史记录会暴露你订阅 GitHub 热榜这一偏好。如果不希望公开运行历史，建议使用私有 GitHub 仓库。

## 凭据泄露处理

1. 立即在 Server酱后台吊销旧 SendKey。
2. 删除或更新 GitHub Actions Secret `SERVERCHAN_SENDKEY`。
3. 如摘要密钥可能泄露，同时在对应服务商处撤销 `SUMMARY_API_KEY`。
4. 检查 Actions 日志和 Git 历史；不要只用新提交覆盖已泄露的值。
5. 生成新密钥后重新执行绑定测试。

