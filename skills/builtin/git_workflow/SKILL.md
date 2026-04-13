---
name: git_workflow
description: Git 日常操作、分支管理、冲突解决、提交规范工作流程
---

# Git Workflow — Git 工作流技能

## 触发词
用户说以下内容时加载本技能：
- git / commit / push / pull / merge / rebase
- 分支管理 / 合并代码 / 解决冲突
- 怎么回滚 / 撤销提交 / 恢复文件

## 常用操作速查

### 查看状态
```bash
git status                    # 查看工作区状态
git log --oneline -10         # 查看最近10条提交
git diff HEAD                 # 查看未暂存的改动
git diff --staged             # 查看已暂存的改动
```

### 提交工作流
```bash
git add -p                    # 交互式暂存（推荐，避免误提交）
git commit -m "type: message" # 提交（遵循 Conventional Commits）
git push origin feature-xxx   # 推送到远程分支
```

### 分支管理
```bash
git checkout -b feature/xxx   # 创建并切换新分支
git branch -d feature/xxx     # 删除已合并分支
git fetch --prune             # 清理已删除的远程分支引用
```

### 撤销操作
```bash
git restore <file>            # 撤销工作区改动（未暂存）
git restore --staged <file>   # 取消暂存（保留改动）
git revert HEAD               # 安全回滚最后一次提交（生成新提交）
git reset --soft HEAD~1       # 撤销提交但保留改动（已暂存）
```

⚠️ 避免对已推送的提交使用 `git reset --hard` 或 `git push --force`（会影响他人）

## Conventional Commits 规范

```
type(scope): description

Types:
  feat     - 新功能
  fix      - Bug 修复
  refactor - 重构（不影响功能）
  docs     - 文档更新
  test     - 测试相关
  chore    - 构建/工具链改动
  perf     - 性能优化
  style    - 代码格式（不影响逻辑）

Examples:
  feat(auth): add JWT token refresh
  fix(api): handle empty response from weather service
  docs(readme): update installation steps
```

## 冲突解决工作流

1. 发生冲突时：`git status` 找到冲突文件
2. 打开文件，找到 `<<<<<<`/`======`/`>>>>>>` 标记
3. 手动选择保留哪个版本（或合并两者）
4. 删除冲突标记，保存文件
5. `git add <file>` 标记已解决
6. `git commit` 完成合并

## 使用 shell_exec 执行 git 命令

```python
# 使用 shell_exec 工具执行 git 操作
shell_exec("git status")
shell_exec("git log --oneline -10")
shell_exec("git diff HEAD")

# 创建提交
shell_exec('git add -A && git commit -m "feat: add new feature"')
```

## 注意事项

- 推送前先 `git pull --rebase` 同步远程改动
- 重要操作前先 `git stash` 保存临时改动
- 生产分支（main/master）禁止直接 push，使用 PR/MR 流程
- `.gitignore` 要在第一次提交前配置好
