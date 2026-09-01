# Sigstore Release Verification

Whitebox Writing Lab 的正式发布产物通过 GitHub Actions OIDC、Fulcio 短期证书和 Rekor 透明日志进行 keyless signing。

## Signed files

每个 Release 应包含：

```text
Whitebox-Writing-<version>-Setup.exe
Whitebox-Writing-<version>-Setup.exe.sigstore.json
whitebox-writing-portable-<version>.zip
whitebox-writing-portable-<version>.zip.sigstore.json
SHA256SUMS
SHA256SUMS.sigstore.json
```

缺少对应 `.sigstore.json` 的文件不应视为正式发布文件。

## Verify

安装 Sigstore CLI：

```bash
python -m pip install sigstore
```

验证下载文件。将 `<tag>` 替换为实际 tag，例如 `v0.4.0`：

```bash
python -m sigstore verify identity \
  --bundle whitebox-writing-portable-0.4.0.zip.sigstore.json \
  --cert-identity "https://github.com/pluteer/whitebox-writing-lab/.github/workflows/release.yml@refs/tags/<tag>" \
  --cert-oidc-issuer "https://token.actions.githubusercontent.com" \
  whitebox-writing-portable-0.4.0.zip
```

安装包验证方式相同，只需替换文件名和 bundle。

再检查 SHA256：

```bash
sha256sum --check SHA256SUMS
```

Windows PowerShell 可以先查看文件哈希：

```powershell
Get-FileHash .\Whitebox-Writing-0.4.0-Setup.exe -Algorithm SHA256
Get-Content .\SHA256SUMS
```

## Trust boundary

- 证书身份必须精确匹配本仓库的 `release.yml` 和发布 tag。
- OIDC issuer 必须是 `https://token.actions.githubusercontent.com`。
- 签名必须能通过 Sigstore 密码学验证；仅存在 bundle 文件不代表验证成功。
- Sigstore 不会把 EXE 转换成 Windows Authenticode 已签名程序。Windows SmartScreen 声誉和 Authenticode 需要另一套商业或企业证书基础设施。
