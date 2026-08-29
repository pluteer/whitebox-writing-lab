# Contributing

感谢参与 Whitebox Writing。

## 开发环境

- Node.js 22+
- Python 3.12+
- WSL 2 + Ubuntu（Windows 用户）

安装依赖：

```bash
npm install
python -m venv apps/api/.venv
apps/api/.venv/bin/pip install -e "apps/api[dev]"
```

运行检查：

```bash
apps/api/.venv/bin/pytest
npm --workspace apps/web run test
npm --workspace apps/web run build
```

## 提交变更

- 一个 Pull Request 只解决一个主题。
- 新增行为应同时补充测试。
- 不要提交数据库、Provider 密钥、虚拟环境、依赖目录或安装包。
- 不要把真实小说原文、用户资产或运行日志提交到仓库。
- 说明变更原因、验证命令和已知限制。

## 安全问题

请不要在公开 Issue 中发布密钥、个人数据或未修复的安全细节。安全问题请按 `SECURITY.md` 联系维护者。
