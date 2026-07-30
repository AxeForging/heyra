#pragma once
#include <cstdint>
#include <cstddef>

// Zero ESP-IDF/Arduino includes — host-testable.
namespace heyra::core {

// Phase 1 has exactly one tone (a critical smoke-alarm-response beep). Unrecognized
// tone_ids fall back to it. Multi-tone palette deferred to Phase 3 — nothing calls other
// tone IDs yet (YAGNI).
enum ToneId : int32_t { TONE_CRITICAL = 0 };

static constexpr float TONE_SAMPLE_RATE_HZ = 16000.0f;

// Total sample count for the given tone (its full duration at TONE_SAMPLE_RATE_HZ).
size_t tone_sample_count(int32_t tone_id);

// Renders up to max_samples of the tone into out, continuing from sample_offset (how many
// samples of this tone have already been rendered/sent so far). Returns samples written,
// 0 once sample_offset >= tone_sample_count(tone_id). Chunked by design — never renders a
// whole multi-second tone into one buffer (no PSRAM headroom for that).
size_t render_tone_chunk(int32_t tone_id, size_t sample_offset, int16_t *out, size_t max_samples);

}  // namespace heyra::core
