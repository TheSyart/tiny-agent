---
name: nano_banana_2
description: 使用 infsh CLI 调用 Google Gemini 3.1 Flash Image Preview 生成或编辑图片
---

# Nano Banana 2 — Gemini 图片生成技能

## 触发词
用户说以下任意词时加载本技能：
- nano banana 2 / nanobanana 2
- gemini 3.1 flash image
- 用 gemini 生成图片
- 生成图片（无其他工具可用时）

## 工具
使用 `shell_exec` 调用 `infsh` CLI。

## 基本用法

### 生成图片
```bash
infsh "详细的图片描述（英文效果更好）"
```

### 编辑/修改已有图片
```bash
infsh --image /path/to/input.jpg "修改指令，例如：make the background blue"
```

### 指定输出路径
```bash
infsh "描述" --output /path/to/output.png
```

## 工作流程

1. 收到图片生成请求
2. 将用户描述翻译/优化为英文 prompt（更精准）
3. 调用 `shell_exec` 执行 infsh 命令
4. 返回生成图片的路径或错误信息
5. 告知用户图片已保存到哪个位置

## Prompt 优化建议

- 具体描述风格：`photorealistic`, `anime style`, `oil painting`, `watercolor`
- 描述光线：`soft morning light`, `dramatic shadows`, `neon lights`
- 描述构图：`close-up portrait`, `wide landscape`, `bird's eye view`
- 避免模糊描述，尽量量化细节

## 示例

用户：帮我生成一张赛博朋克城市夜景
```bash
infsh "cyberpunk city at night, neon lights reflecting on wet streets, towering skyscrapers, futuristic vehicles, cinematic lighting, photorealistic 8k"
```

用户：把这张图的背景改成海边
```bash
infsh --image ./photo.jpg "replace the background with a beautiful ocean beach at sunset, keep the subject unchanged"
```

## 错误处理

- 若 `infsh` 未安装：提示用户安装 infsh CLI
- 若生成失败：检查 API key 是否配置，重试一次
- 若输出路径不存在：自动使用当前目录 `./output.png`
