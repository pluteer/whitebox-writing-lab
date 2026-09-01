# Security Policy

## Reporting a vulnerability

请不要在公开 Issue 中提交 API Key、数据库、用户原文或可利用的安全细节。

目前项目处于早期开发阶段。请通过 GitHub Security Advisories 私下报告安全问题；如果仓库尚未启用该功能，请联系仓库维护者并提供：

- 受影响的版本或提交。
- 可复现步骤。
- 影响范围。
- 建议的修复方向（如有）。

## Local secrets

Provider 密钥只应保存在本机 `data/provider-secrets.json` 或环境变量中。提交前请确认 `git status` 和 `git diff --cached` 中没有密钥、数据库或用户内容。

## Release signatures

`v0.4.1` 起，Windows 安装包、便携包和 `SHA256SUMS` 使用 Sigstore keyless signing。签名身份由 GitHub Actions OIDC 和 Fulcio 短期证书绑定到本仓库的 `.github/workflows/release.yml`，并写入透明日志。每个发布文件必须同时带有 `<filename>.sigstore.json`；缺少 bundle 的文件不是正式发布产物。

Sigstore 证明软件供应链来源和文件完整性，不等同于 Windows Authenticode。Windows 资源管理器可能仍显示“未知发布者”；用户应按 [`docs/SIGSTORE.md`](docs/SIGSTORE.md) 验证发布材料。
