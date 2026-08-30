# Versioning

项目使用 Semantic Versioning：`MAJOR.MINOR.PATCH`。

## 唯一版本源

当前版本只在根目录 `version.json` 中维护：

```json
{
  "version": "0.3.0"
}
```

更新版本时，先修改 `version.json`，然后运行：

```bash
python tools/check_version.py
```

检查通过后再提交代码、创建 Git tag 和发布 Release。

## 版本规则

- `PATCH`：修复问题，不改变公开 API 或数据契约。
- `MINOR`：增加向后兼容的新能力。
- `MAJOR`：存在不兼容的 API、数据或运行行为变化。
- Git tag 必须使用 `vMAJOR.MINOR.PATCH`，例如 `v0.3.0`。
- GitHub Release 的 tag、标题、安装包和便携包版本必须一致。
- 不要手动修改数据库、密钥、日志或用户项目来“升级版本”。

## 发布流程

```text
修改 version.json
→ python tools/check_version.py
→ 运行后端和前端测试
→ 构建便携包/安装包
→ 创建 vX.Y.Z tag
→ 创建同名 GitHub Release
→ 上传同版本构建产物和 SHA256
```

发布前不得把未签名或未验证的构建产物标记为正式稳定版。数字签名状态必须在 Release 说明中明确。
