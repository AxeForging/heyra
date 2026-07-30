#include "goertzel.h"
#include <cmath>

namespace heyra::core {

namespace {
constexpr float PI_F = 3.14159265358979323846f;
// Amplitude threshold (int16 units, full scale 32767) for "beep present" in a window.
// ponytail: fixed cutoff, no adaptive noise floor — tune this one constant empirically
// during hardware bring-up before reaching for anything smarter.
//
// Measured on real hardware (ATOM Echo SPM1423 PDM mic, 2026-07-30): ambient noise floor
// sits under ~1.0, a 3kHz test tone played from a couple meters away peaked at ~10-14.
// 4.0 sits with margin above the noise floor and well below observed signal — revisit
// against a real smoke-alarm T3 recording during Phase 4 calibration.
constexpr float BEEP_AMPLITUDE_THRESHOLD = 4.0f;
}  // namespace

GoertzelFilterBank::GoertzelFilterBank() {
  for (int i = 0; i < GOERTZEL_NUM_BINS; i++) {
    float k = roundf(static_cast<float>(GOERTZEL_WINDOW_SAMPLES) * GOERTZEL_TARGET_HZ[i] / GOERTZEL_SAMPLE_RATE_HZ);
    float omega = (2.0f * PI_F * k) / static_cast<float>(GOERTZEL_WINDOW_SAMPLES);
    bins_[i].coeff = 2.0f * cosf(omega);
  }
}

bool GoertzelFilterBank::process_sample(int16_t sample, float *out_mags) {
  float s = static_cast<float>(sample);
  for (int i = 0; i < GOERTZEL_NUM_BINS; i++) {
    BinState &b = bins_[i];
    float q0 = b.coeff * b.q1 - b.q2 + s;
    b.q2 = b.q1;
    b.q1 = q0;
  }

  sample_count_++;
  if (sample_count_ < GOERTZEL_WINDOW_SAMPLES) {
    return false;
  }

  for (int i = 0; i < GOERTZEL_NUM_BINS; i++) {
    BinState &b = bins_[i];
    // Standard Goertzel power formula; steady-state |power| ~= (N*A/2)^2 for a pure tone
    // at the target bin, so sqrt(power) * 2/N recovers an amplitude estimate A.
    float power = b.q1 * b.q1 + b.q2 * b.q2 - b.q1 * b.q2 * b.coeff;
    out_mags[i] = sqrtf(power > 0.0f ? power : 0.0f) * (2.0f / GOERTZEL_WINDOW_SAMPLES);
    b.q1 = 0.0f;
    b.q2 = 0.0f;
  }
  sample_count_ = 0;
  return true;
}

bool is_beep_present(const float *mags) {
  for (int i = 0; i < GOERTZEL_NUM_BINS; i++) {
    if (mags[i] > BEEP_AMPLITUDE_THRESHOLD) {
      return true;
    }
  }
  return false;
}

}  // namespace heyra::core
