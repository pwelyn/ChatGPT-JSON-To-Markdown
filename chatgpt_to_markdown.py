#!/usr/bin/env python3
"""
ChatGPT JSON -> Markdown 转换器（支持单文件 / 批量目录）

用法：
    # 单文件模式：输入 .json 文件，输出同目录同名 .md（或指定输出路径）
    python3 chatgpt_to_markdown.py conversation.json
    python3 chatgpt_to_markdown.py conversation.json /path/to/output/

    # 批量模式：输入目录，输出到指定目录
    python3 chatgpt_to_markdown.py input_dir/ output_dir/

    # 无参数：默认 chatgpt_team_backup/ -> chatgpt_team_backup_md/
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


# 北京时间
CST = timezone(timedelta(hours=8))

ROLE_LABELS = {
    "user": "👤 User",
    "assistant": "🤖 Assistant",
    "tool": "🔧 Tool",
}


def ts_to_str(ts):
    """Unix timestamp -> 可读时间字符串（北京时间）"""
    if ts is None:
        return None
    try:
        dt = datetime.fromtimestamp(ts, tz=CST)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return None


def build_conversation_chain(data):
    """
    从 mapping 中按 parent->children 链路构建有序消息列表。
    仅保留 user / assistant / tool 角色的可见消息。
    """
    mapping = data.get("mapping", {})
    current_node_id = data.get("current_node")

    # 策略：从 current_node 回溯到根，得到主线路径
    if not current_node_id or current_node_id not in mapping:
        # fallback: 找到没有 parent 的根节点，然后沿第一个 child 走到底
        root_ids = [nid for nid, node in mapping.items() if node.get("parent") is None]
        if not root_ids:
            return []
        chain = []
        current = root_ids[0]
        while current:
            chain.append(current)
            children = mapping[current].get("children", [])
            current = children[0] if children else None
    else:
        # 从 current_node 回溯
        path = []
        nid = current_node_id
        while nid:
            path.append(nid)
            nid = mapping[nid].get("parent")
        chain = list(reversed(path))

    # 过滤出可见的 user / assistant / tool 消息
    messages = []
    for nid in chain:
        node = mapping[nid]
        msg = node.get("message")
        if msg is None:
            continue

        # 跳过隐藏的系统消息
        meta = msg.get("metadata", {})
        if meta.get("is_visually_hidden_from_conversation"):
            continue

        role = msg.get("author", {}).get("role", "")
        if role not in ("user", "assistant", "tool"):
            continue

        content = msg.get("content", {})
        content_type = content.get("content_type", "")

        # 提取文本
        text = ""
        if content_type == "text":
            parts = content.get("parts", [])
            text = "\n".join(str(p) for p in parts if p)
        elif content_type == "code":
            text = content.get("text", "")
        elif content_type == "execution_output":
            text = content.get("text", "")
        elif content_type == "multimodal_text":
            parts = content.get("parts", [])
            text_parts = []
            for p in parts:
                if isinstance(p, str):
                    text_parts.append(p)
                elif isinstance(p, dict):
                    # 图片等多模态内容
                    asset_pointer = p.get("asset_pointer", "")
                    if asset_pointer:
                        text_parts.append(f"![image]({asset_pointer})")
                    else:
                        text_parts.append("[多模态内容]")
            text = "\n".join(text_parts)
        elif content_type == "user_editable_context":
            # 自定义指令，跳过
            continue
        elif content_type == "reasoning_recap":
            # 思考过程摘要，跳过
            continue
        else:
            parts = content.get("parts", [])
            if parts:
                text = "\n".join(str(p) for p in parts if p)

        if not text.strip():
            continue

        messages.append({
            "role": role,
            "text": text.strip(),
            "create_time": msg.get("create_time"),
            "model": meta.get("model_slug") or meta.get("resolved_model_slug"),
        })

    return messages


def json_to_markdown(json_path):
    """将单个 ChatGPT JSON 导出文件转为 Markdown 字符串。"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    title = data.get("title", Path(json_path).stem)
    create_time = ts_to_str(data.get("create_time"))
    update_time = ts_to_str(data.get("update_time"))
    model = data.get("default_model_slug", "")
    conv_id = data.get("conversation_id", "")

    messages = build_conversation_chain(data)

    # 构建 Markdown
    lines = []
    lines.append(f"# {title}\n")

    # YAML-like 元信息块
    meta_items = []
    if create_time:
        meta_items.append(f"- **创建时间**: {create_time}")
    if update_time:
        meta_items.append(f"- **更新时间**: {update_time}")
    if model:
        meta_items.append(f"- **模型**: {model}")
    if conv_id:
        meta_items.append(f"- **会话 ID**: `{conv_id}`")
    meta_items.append(f"- **消息数**: {len(messages)}")

    if meta_items:
        lines.append("\n".join(meta_items))
        lines.append("")

    lines.append("---\n")

    # 消息
    for i, msg in enumerate(messages):
        role_label = ROLE_LABELS.get(msg["role"], msg["role"])
        time_str = ts_to_str(msg["create_time"])
        model_str = msg.get("model") or ""

        # 标题行
        header_parts = [f"## {role_label}"]
        annotations = []
        if time_str:
            annotations.append(time_str)
        if model_str and msg["role"] == "assistant":
            annotations.append(model_str)
        if annotations:
            header_parts.append(f"  <sub>{' · '.join(annotations)}</sub>")

        lines.append("".join(header_parts))
        lines.append("")
        lines.append(msg["text"])
        lines.append("")

        if i < len(messages) - 1:
            lines.append("---\n")

    return "\n".join(lines)


def convert_single(json_path, output_arg=None):
    """转换单个 JSON 文件为 Markdown。"""
    json_path = Path(json_path)

    if output_arg:
        out = Path(output_arg)
        if out.suffix == ".md":
            md_path = out
        else:
            out.mkdir(parents=True, exist_ok=True)
            md_path = out / (json_path.stem + ".md")
    else:
        md_path = json_path.with_suffix(".md")

    md_content = json_to_markdown(json_path)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"✅ {json_path.name} -> {md_path}")


def convert_batch(input_dir, output_dir):
    """批量转换目录下所有 JSON 文件。"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_path.glob("*.json"))
    if not json_files:
        print(f"⚠️  未在 {input_path} 中找到 .json 文件")
        sys.exit(0)

    print(f"📂 输入目录: {input_path}")
    print(f"📁 输出目录: {output_path}")
    print(f"📄 发现 {len(json_files)} 个 JSON 文件\n")

    success = 0
    failed = 0
    for jf in json_files:
        md_name = jf.stem + ".md"
        md_path = output_path / md_name
        try:
            md_content = json_to_markdown(jf)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            print(f"  ✅ {jf.name} -> {md_name}")
            success += 1
        except Exception as e:
            print(f"  ❌ {jf.name} 转换失败: {e}")
            failed += 1

    print(f"\n🏁 完成: {success} 成功, {failed} 失败")


def main():
    script_dir = Path(__file__).parent

    if len(sys.argv) < 2:
        # 无参数：默认批量模式
        convert_batch(script_dir / "chatgpt_team_backup", script_dir / "chatgpt_team_backup_md")
        return

    input_arg = sys.argv[1]
    input_path = Path(input_arg) if Path(input_arg).is_absolute() else script_dir / input_arg

    if not input_path.exists():
        print(f"❌ 输入路径不存在: {input_path}")
        sys.exit(1)

    output_arg = sys.argv[2] if len(sys.argv) > 2 else None
    if output_arg and not Path(output_arg).is_absolute():
        output_arg = str(script_dir / output_arg)

    if input_path.is_file() and input_path.suffix == ".json":
        # 单文件模式
        convert_single(input_path, output_arg)
    elif input_path.is_dir():
        # 批量目录模式
        out = output_arg or str(input_path) + "_md"
        convert_batch(input_path, out)
    else:
        print(f"❌ 输入必须是 .json 文件或目录: {input_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
