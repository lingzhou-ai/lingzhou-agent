"""Hello World 示例插件。"""

def register(ctx):
    """注册工具。"""
    from tools.registry import tool, ToolManifest, ToolResult, ToolParam, ToolContext
    from typing import Any

    @tool(ToolManifest(
        name="hello.greet",
        description="打招呼",
        progress_category="info",
        params=[ToolParam("name", "string", "名字", required=False)],
    ))
    async def hello_greet(params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        name = params.get("name") or "灵舟"
        return ToolResult(summary=f"你好，{name}！这是来自插件的问候 👋")


def unregister():
    """移除工具。"""
    pass
