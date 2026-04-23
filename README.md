# Foxtrai MCP Server

基于 [FastMCP](https://github.com/PrefectHQ/fastmcp) 框架实现的 Foxtrai AI 绘画平台 MCP Server。

## 功能

- **upload_image** — 上传本地图片作为参考图/垫图
- **create_drawing_task** — 提交 AI 绘画任务
- **get_task_status** — 查询任务状态和结果
- **generate_image** — 一键生成（自动轮询等待结果）
- **list_tasks** — 查看历史任务列表
- **list_assets** — 查看图片资源列表
- **delete_asset** — 删除图片资源

支持模型：`nano-banana`、`nano-banana-pro`、`nano-banana-pro-ultra`、`nano-banana-2`

## 安装

```bash
git clone git@github.com:liuruing/foxtrai-mcp.git
cd foxtrai-mcp
uv sync
```

## 接入 Claude Code

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "foxtrai": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/foxtrai-mcp", "python", "-m", "foxtrai_mcp"],
      "env": {
        "FOXTRAI_TOKEN": "your_token_here"
      }
    }
  }
}
```

> 将 `/path/to/foxtrai-mcp` 替换为实际克隆路径，`your_token_here` 替换为你的 API Token。

配置后重启 Claude Code，即可在对话中使用绘画相关工具。

## 接入 Codex (OpenAI Codex CLI)

Codex CLI 同样支持 MCP Server。在 `~/.codex/config.json` 中添加：

```json
{
  "mcpServers": {
    "foxtrai": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/foxtrai-mcp", "python", "-m", "foxtrai_mcp.server"],
      "env": {
        "FOXTRAI_TOKEN": "your_token_here"
      }
    }
  }
}
```

## 接入 Cursor

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "foxtrai": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/foxtrai-mcp", "python", "-m", "foxtrai_mcp.server"],
      "env": {
        "FOXTRAI_TOKEN": "your_token_here"
      }
    }
  }
}
```

## 直接运行

```bash
# stdio 模式（供 MCP 客户端连接）
FOXTRAI_TOKEN=your_token_here uv run python -m foxtrai_mcp.server

# SSE 模式（HTTP 服务）
FOXTRAI_TOKEN=your_token_here uv run python -c "from foxtrai_mcp.server import mcp; mcp.run(transport='sse', host='0.0.0.0', port=8000)"
```

## 使用示例

接入后，你可以在 Claude / Codex 中直接说：

- "用 nano-banana-pro 模型生成一张赛博朋克风格的城市夜景，16:9 比例"
- "上传这张图片作为参考图，然后基于它生成一张类似风格的新图"
- "查看我最近的绘画任务状态"
- "列出所有已生成的图片"

## License

MIT
