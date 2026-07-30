#include "tone_synth.h"
#include <cmath>
#include <algorithm>

namespace heyra::core {

namespace {
constexpr float TONE_CRITICAL_HZ = 3000.0f;             // mid-band per spec's 2.5-3.5kHz alert range
constexpr float TONE_CRITICAL_DURATION_S = 1.5f;
constexpr int16_t TONE_CRITICAL_AMPLITUDE = 30000;       // near-0dBFS, small headroom under int16 max
constexpr float FADE_S = 0.005f;                         // 5ms fade in/out to avoid a click

size_t tone_critical_sample_count() {
  return static_cast<size_t>(TONE_CRITICAL_DURATION_S * TONE_SAMPLE_RATE_HZ);
}

// A square wave centered at 0 has no low-frequency content by construction (only odd
// harmonics >= the fundamental), so it's inherently high-passed relative to the alert
// band already — no separate HPF stage needed for this single synthesized tone.
int16_t tone_critical_sample(size_t sample_index, size_t total_samples) {
  float period_samples = TONE_SAMPLE_RATE_HZ / TONE_CRITICAL_HZ;
  bool high = fmodf(static_cast<float>(sample_index), period_samples) < (period_samples / 2.0f);

  size_t fade_samples = static_cast<size_t>(FADE_S * TONE_SAMPLE_RATE_HZ);
  float gain = 1.0f;
  if (fade_samples > 0) {
    if (sample_index < fade_samples) {
      gain = static_cast<float>(sample_index) / fade_samples;
    } else if (total_samples - sample_index < fade_samples) {
      gain = static_cast<float>(total_samples - sample_index) / fade_samples;
    }
  }
  return static_cast<int16_t>((high ? TONE_CRITICAL_AMPLITUDE : -TONE_CRITICAL_AMPLITUDE) * gain);
}

}  // namespace

size_t tone_sample_count(int32_t tone_id) {
  (void) tone_id;
  return tone_critical_sample_count();
}

size_t render_tone_chunk(int32_t tone_id, size_t sample_offset, int16_t *out, size_t max_samples) {
  (void) tone_id;
  size_t total = tone_critical_sample_count();
  if (sample_offset >= total) {
    return 0;
  }
  size_t n = std::min(max_samples, total - sample_offset);
  for (size_t i = 0; i < n; i++) {
    out[i] = tone_critical_sample(sample_offset + i, total);
  }
  return n;
}

}  // namespace heyra::core
