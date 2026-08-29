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
