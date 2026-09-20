# Chunk / Image 简化审核表

本次只保留最必要的六列：

```text
题号
题目
所属产品
当前chunkid列表
图片id列表
是否修改
```

Dev：`dev/DEV_CHUNK_IMAGE_REVIEW.csv`

Heldout：`heldout/HELDOUT_CHUNK_IMAGE_REVIEW.csv`

## 如何审核

1. 打开对应 CSV，按题号找到题目。
2. 复制或搜索 `当前chunkid列表` 中的 Chunk ID。
3. 根据 Chunk ID 中的 `_small_`、`_mid_`、`_big_` 判断层级。
4. 打开对应原始 Markdown 和分块 JSONL，检查这些 Chunk 是否属于正确手册、章节和证据范围。
5. 打开图片 ID 对应的图片，检查是否属于正确产品和问题。
6. 如果当前列表正确，在 `是否修改` 填 `否`。
7. 如果需要修改，直接在 `当前chunkid列表` 或 `图片id列表` 中替换为你确认后的列表，并在 `是否修改` 填 `是`。

`所属产品` 来自当前 Candidate Chunk 的 `product_name`（缺失时回退到 `doc_name`），不是根据题目调用模型猜测出来的产品分类。若一题包含多本产品手册，会用 `；` 分隔。

当前表是审核工作表，不会自动写回 `DEV_GOLD_REVIEW.csv` 或 `HELDOUT_GOLD_REVIEW.csv`。审核完成后保留这两个 CSV，再进行同步和正式 Gold 字段审核。

## 原始 Markdown 文档

中文手册：

```text
data/ch-manual/*.md
```

英文手册：

```text
data/en-manual/*.md
```

## 当前 Candidate 分块文件

每个手册一个目录：

```text
process/artifacts/manuals/<manual_artifact_id>/small_chunks.jsonl
process/artifacts/manuals/<manual_artifact_id>/mid_chunks.jsonl
process/artifacts/manuals/<manual_artifact_id>/big_chunks.jsonl
process/artifacts/manuals/<manual_artifact_id>/manifest.json
```

`manifest.json` 记录该目录对应的手册名和各层 Chunk 数量。旧 artifact 中的绝对 `source_path` 可能来自构建机器；人工审核应以仓库内 `data/ch-manual/`、`data/en-manual/` 和 Chunk 的 `doc_name`、`source_span` 为准。

在 JSONL 中搜索 `chunk_id`，重点查看：

```text
doc_name
source_span
header_path
section_title
content
```

`source_span.start_line` 和 `source_span.end_line` 可回到 `data/ch-manual/*.md` 或 `data/en-manual/*.md` 对照原文。

图片通常位于：

```text
process/data/插图/<image_id>.<jpg|jpeg|png|webp>
```

## 注意

这里列出的 Chunk 是 Source Evidence 派生的 Candidate 映射，不是运行时 Retrieval TopK，也不包含 rank 或 score。不要根据系统回答或检索结果决定 Gold。
