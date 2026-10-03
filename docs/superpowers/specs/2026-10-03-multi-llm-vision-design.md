# Multi-LLM Vision Bridge — Design Doc

- **Ngày:** 2026-10-03
- **Branch:** `feat/multi-llm-vision`
- **Quyết định user:** chỉ vision bridge (JEV giữ TYPESAFE_API_KEY riêng); hỗ trợ cả OpenAI-style lẫn Anthropic-style.

## 1. Mục tiêu

Cho phép vision bridge (đọc screenshot → observation JSON) dùng **bất kỳ LLM endpoint nào** qua 3 biến môi trường:

| Env | Ý nghĩa |
|---|---|
| `MODEL_NAME` | tên model tại endpoint (VD `qwen2.5-vl-72b`, `gpt-4o-mini`, `claude-haiku-4-5`) |
| `LLM_URL` | base URL endpoint (VD `http://localhost:11434/v1`, `https://openrouter.ai/api/v1`, `https://gateway.internal/v1/messages`) |
| `LLM_API_KEY` | key — **tùy chọn** (Ollama/vLLM local không cần) |

**Ưu tiên**: `LLM_URL` + `MODEL_NAME` set → generic bridge. Không set → fallback đường Anthropic gốc (`ANTHROPIC_API_KEY` + Haiku pin) như hiện tại. Không có gì → vision checks SKIPPED.

**Giao thức** (`LLM_STYLE=openai|anthropic`, tùy chọn):
- Mặc định auto: URL chứa `/v1/messages` → anthropic-style; ngược lại → openai-style.
- Openai-style: `POST {LLM_URL}/chat/completions` (nếu URL chưa kết thúc bằng `/chat/completions`), header `Authorization: Bearer` (nếu có key), ảnh dạng `{"type":"image_url","image_url":{"url":"data:<media>;base64,<data>"}}`, response `choices[0].message.content` (str hoặc list parts — join text).
- Anthropic-style: `POST {LLM_URL}` nếu URL đã kết thúc `/messages`, ngược lại `{LLM_URL}/v1/messages`; headers `x-api-key` (nếu có) + `anthropic-version: 2023-06-01`; body giống SDK hiện tại; response `content` parts.

`MODEL_NAME` (env) override `policy.yaml vision.model` khi cả hai cùng tồn tại.

## 2. Kiến trúc

```
vision/claude_bridge.py  — giữ nguyên VisionBridge (Anthropic SDK) + tách helper dùng chung
                            thành module-level: _normalize_obs(obs, keys), (đã có _extract_json,
                            _sniff_media_type, prompts, OBS keys)
vision/generic_bridge.py — GenericVisionBridge: cùng interface (observe/observe_detailed/calls,
                            VisionUnavailable), 2 style request bằng httpx, retry/lock/OSError
                            handling mirror claude_bridge
vision/__init__.py       — make_vision_bridge(max_tokens=2048) -> VisionBridge|GenericVisionBridge|None
__main__.py              — cả 2 subcommand dùng make_vision_bridge(); key-check check-screenshots:
                            (LLM_URL và MODEL_NAME) hoặc ANTHROPIC_API_KEY
```

Lưu ý: model text-only (không đọc ảnh) sẽ fail observation → mỗi ảnh thành error — hành vi đúng (model phải multimodal). Ghi chú trong README.

## 3. Error handling (mirror claude_bridge)

- Đọc file OSError → `VisionUnavailable`
- HTTP non-2xx / timeout / lỗi mạng → retry (1 lần mặc định, sleep 0.5*(attempt+1), không sleep lần cuối) → `VisionUnavailable` chain exception gốc
- Response không parse được JSON (sau khi strip fence) → ValueError kèm text[:200] → retry → `VisionUnavailable`
- normalize: đủ keys theo style prompt (OBS_KEY / OBS_DETAIL_KEYS), list-keys → `[]`, còn lại `"none"`; non-dict → ValueError

## 4. Testing (TDD, mock httpx)

- factory: các tổ hợp env (LLM_URL+MODEL_NAME→generic style auto/override; thiếu 1 trong 2→fallback anthropic; không gì→None)
- openai-style: payload shape (model, image_url data URI với media sniff, prompt text, max_tokens), header Bearer khi có key / không có khi None, parse choices str + list-parts, retry→VisionUnavailable, calls counter
- anthropic-style: URL nối `/v1/messages`, headers x-api-key + version, parse content parts
- normalize reuse qua cả 2 prompt set
- CLI: check-screenshots exit 2 chỉ khi không có nguồn vision nào; run branch dùng factory

## 5. Non-goals

- Không đổi JEV client (TYPESAFE_API_KEY, api.typesafe.ai)
- Không streaming, không tool-use; single-part text response
- Không tự detect multimodal capability của MODEL_NAME
