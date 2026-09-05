"""Structured user-image understanding via a vision LLM (phase 2, off = baseline).

The VLM extracts only directly observable facts from user-uploaded images —
per-field confidence and evidence, never a guessed model number. The whole
module is best-effort: any failure degrades to None and the answer pipeline
runs exactly as it would without images (mirrors the KG-expansion fallback).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from .config import QASettings
from .utils import extract_json, get_openai_client, image_to_data_url, load_prompt, resolve_model_name

log = logging.getLogger(__name__)

_FIELD_LABELS = {
    "product_category": "产品类别",
    "ocr_text": "图中文字",
    "indicator_status": "指示灯/屏幕状态",
    "visible_components": "可见部件",
    "appearance_anomaly": "外观异常",
}


class VLMField(BaseModel):
    """One observable attribute with its own confidence and visual evidence."""
    value: str = ""
    confidence: float = 0.0
    evidence: str = ""


class VLMExtraction(BaseModel):
    """Field-wise structured observation of user images (no model guessing)."""
    product_category: VLMField = VLMField()
    ocr_text: VLMField = VLMField()
    indicator_status: VLMField = VLMField()
    visible_components: VLMField = VLMField()
    appearance_anomaly: VLMField = VLMField()

    def _fields(self) -> list[tuple[str, VLMField]]:
        return [(name, getattr(self, name)) for name in _FIELD_LABELS]

    def to_query_text(self, *, threshold: float) -> str:
        """Short retrieval suffix built from confident fields only (<=200 chars)."""
        parts: list[str] = []
        for name, f in self._fields():
            if f.confidence >= threshold and f.value.strip():
                value = f.value.strip()
                if name == "ocr_text":
                    value = value[:120]
                parts.append(f"{_FIELD_LABELS[name]}:{value}")
        if not parts:
            return ""
        return ("图片观察: " + "；".join(parts))[:200]

    def to_prompt_block(self, *, threshold: float) -> str:
        """Full five-field block for generation prompts, with inline conflict rules."""
        category = self.product_category.value.strip()
        lines: list[str] = []
        # The consistency check leads the block: buried at the tail, generation
        # models answer the text question and never mention the mismatch.
        lines.append(
            "【回答前必须核对】用户上传了现场图片"
            + (f"，图片显示的产品类别为「{category}」" if category else "")
            + "。请先核对用户问题中描述的产品/现象与下方图片观察是否一致："
        )
        lines.append(
            "若不一致（例如问题问的是洗碗机、图片却是空调），必须在**答案开头**明确指出这一差异"
            "并建议用户确认，之后再回答文字问题本身；不要假装没有看到图片。"
        )
        lines.append("")
        lines.append("视觉观察结果（逐字段置信度与依据）：")
        for name, f in self._fields():
            if not f.value.strip():
                lines.append(f"- {_FIELD_LABELS[name]}: （未观察到）")
                continue
            tag = "" if f.confidence >= threshold else "（低置信度，仅供参考）"
            lines.append(
                f"- {_FIELD_LABELS[name]}: {f.value.strip()}{tag}"
                f" ｜置信度 {f.confidence:.2f}｜依据: {f.evidence.strip() or '未说明'}"
            )
        lines.append("")
        lines.append("其他规则：优先采信高置信度观察；不得依据图片外观猜测具体型号，只有图中可读文字可用。")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def understand_images(
    image_paths: list[str] | None,
    question: str,
    *,
    settings: QASettings,
    telemetry: Any | None = None,
) -> VLMExtraction | None:
    """
    Run one VLM call over all user images and parse the structured observation.

    Best-effort only: disabled config, missing images, transport errors, or
    malformed JSON all degrade to None so the QA pipeline never blocks on VLM.
    """
    config = settings.vlm
    if not config.enabled or not image_paths:
        return None

    try:
        client = get_openai_client(
            settings.vlm_llm.env_file,
            settings.vlm_llm.api_key_env,
            settings.vlm_llm.base_url_env,
        )
        model = resolve_model_name(
            settings.vlm_llm.env_file,
            settings.vlm_llm.model_name,
            settings.vlm_llm.model_name_env,
        )
        prompt = load_prompt("vlm_understand.md").format(question=question)

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for path in image_paths:
            content.append({"type": "image_url", "image_url": {"url": image_to_data_url(path)}})

        last_error: Exception | None = None
        for attempt in range(max(1, config.max_retries + 1)):
            call_started = time.monotonic()
            response = None
            try:
                response = client.with_options(timeout=config.timeout_seconds).chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )
                raw = (response.choices[0].message.content or "").strip()
                result = VLMExtraction.model_validate(extract_json(raw))
                if telemetry:
                    telemetry.model_call(stage="vlm", model=model, elapsed_ms=(time.monotonic() - call_started) * 1000, response=response, attempt=attempt + 1)
                return result
            except Exception as exc:
                if telemetry:
                    telemetry.model_call(stage="vlm", model=model, elapsed_ms=(time.monotonic() - call_started) * 1000, response=response, error=exc, attempt=attempt + 1)
                last_error = exc
        raise RuntimeError(f"VLM call failed after retries: {last_error}")
    except Exception as exc:
        log.warning("VLM understanding failed, continuing without: %s", exc)
        if telemetry:
            telemetry.fallback("vlm_disabled_after_error")
        return None
