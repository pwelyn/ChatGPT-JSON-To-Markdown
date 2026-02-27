# ChatGPT-JSON-To-Markdown
**ChatGPT JSON -> Markdown 转换器（支持单文件 / 批量目录）**
# 用法：
## 单文件模式：输入 .json 文件，输出同目录同名 .md（或指定输出路径）
```python
python3 chatgpt_to_markdown.py conversation.json
```
```python
python3 chatgpt_to_markdown.py conversation.json /path/to/output/
```
## 批量模式：输入目录，输出到指定目录
```python
python3 chatgpt_to_markdown.py input_dir/ output_dir/
```
## 无参数：默认 chatgpt_team_backup/ -> chatgpt_team_backup_md/
