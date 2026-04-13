---
name: web_research
description: 使用 web_search 工具进行高效网络调研的策略与工作流程
---

# Web Research — 网络调研技能

## 触发词
用户说以下内容时加载本技能：
- 搜索 / 查一下 / 上网查
- 帮我找资料 / 调研一下
- 最新进展 / 最近发布 / 最新消息
- 怎么用 / 如何安装 / 官方文档在哪

## 工作流程

### 基本搜索策略

1. **分解查询**：将复杂问题拆成 2-3 个子查询
   - 宽泛查询获取概览：`"Python async best practices 2024"`
   - 精确查询获取细节：`"asyncio gather vs create_task difference"`

2. **关键词优化**：
   - 加年份限定时效性：`"React 18 features 2024"`
   - 加 "site:" 限定来源：`"site:github.com asyncio examples"`
   - 加引号精确匹配：`'"connection pool" python postgresql"`

3. **多轮迭代**：
   - 第一轮：获取概览和权威来源
   - 第二轮：针对具体细节深入搜索
   - 第三轮：验证关键事实（如版本号、API 名称）

### 结果处理

1. 优先使用官方文档、GitHub 仓库、知名技术博客
2. 对比多个来源，避免单一信息源偏差
3. 注意发布日期，技术类信息以最新为准
4. 整合结果时注明来源 URL

## 示例

用户：帮我查一下 FastAPI 最新版本和主要特性
```
# 搜索1：获取版本信息
web_search("FastAPI latest version release 2024")

# 搜索2：获取特性概览  
web_search("FastAPI features async python web framework")

# 整合：从官方 GitHub/文档页面提取关键信息
```

用户：搜索 Claude API 的 tool use 使用方法
```
# 精确搜索官方文档
web_search("Anthropic Claude API tool use function calling documentation")

# 如有必要，搜索示例代码
web_search("Claude tool use python example site:github.com")
```

## 注意事项

- `web_search` 返回的是摘要片段，非完整页面内容
- 遇到需要完整文档的情况，建议用户直接访问 URL
- 搜索结果可能有时效性，重要事实需标注来源和日期
- 每次搜索 `max_results=5` 即可，过多结果反而难以整合
