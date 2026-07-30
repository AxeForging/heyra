#pragma once
#include <cstdint>
#include <cstddef>

// Zero ESP-IDF/Arduino includes — host-testable.
namespace heyra::core {

static constexpr size_t GOERTZEL_WINDOW_SAMPLES = 1024;  // 64ms @ 16kHz, per spec
static constexpr int GOERTZEL_NUM_BINS = 3;
static constexpr float GOERTZEL_TARGET_HZ[GOERTZEL_NUM_BINS] = {3000.0f, 3200.0f, 3400.0f};
static constexpr float GOERTZEL_SAMPLE_RATE_HZ = 16000.0f;

// Runs 3 Goertzel filters (3.0/3.2/3.4kHz) in parallel over a 64ms sliding window.
class GoertzelFilterBank {
 public:
  GoertzelFilterBank();

  // Feed one PCM sample. Returns true when a 1024-sample window completes; on that call
  // out_mags[0..2] holds each bin's estimated amplitude (same linear units as the input
  // samples — e.g. ~3000 means "a 3kHz-band tone at roughly amplitude 3000 out of int16
  // full scale 32767"), making the threshold in is_beep_present human-tunable.
  bool process_sample(int16_t sample, float *out_mags);

 private:
  struct BinState {
    float coeff{0.0f};
    float q1{0.0f};
    float q2{0.0f};
  };
  BinState bins_[GOERTZEL_NUM_BINS];
  size_t sample_count_{0};
};

// Fixed-threshold "is any of the 3 bins loud enough to call this a beep" test.
// Placeholder threshold — expect to tune this once against a real T3 recording during
// hardware bring-up (see docs/build-plan.md risk notes / the Phase 1 plan).
bool is_beep_present(const float *mags);

}  // namespace heyra::core
