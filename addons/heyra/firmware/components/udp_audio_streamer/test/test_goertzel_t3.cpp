// Host-only test for the Goertzel filter bank + T3 pattern detector. No ESP-IDF/Arduino,
// no test framework — plain assert(), built with build_test.sh. This is the "one runnable
// check" for udp_audio_streamer's smoke-alarm detection logic.
#include <cassert>
#include <cmath>
#include <cstdio>
#include <vector>

#include "../goertzel.h"
#include "../t3_detector.h"

using namespace heyra::core;

namespace {

std::vector<int16_t> sine_burst(float hz, size_t n_samples, int16_t amplitude) {
  std::vector<int16_t> out(n_samples);
  for (size_t i = 0; i < n_samples; i++) {
    out[i] = static_cast<int16_t>(amplitude * sinf(2.0f * static_cast<float>(M_PI) * hz * static_cast<float>(i) /
                                                     GOERTZEL_SAMPLE_RATE_HZ));
  }
  return out;
}

void test_goertzel_selectivity() {
  GoertzelFilterBank target_bank;
  float target_mags[GOERTZEL_NUM_BINS] = {0};
  auto target_tone = sine_burst(3000.0f, GOERTZEL_WINDOW_SAMPLES, 20000);
  for (size_t i = 0; i < target_tone.size(); i++) {
    bool complete = target_bank.process_sample(target_tone[i], target_mags);
    assert(complete == (i == target_tone.size() - 1));
  }

  GoertzelFilterBank control_bank;
  float control_mags[GOERTZEL_NUM_BINS] = {0};
  auto control_tone = sine_burst(1000.0f, GOERTZEL_WINDOW_SAMPLES, 20000);
  for (size_t i = 0; i < control_tone.size(); i++) {
    control_bank.process_sample(control_tone[i], control_mags);
  }

  // Bin 0 (3.0kHz) is exactly on-target for the 3000Hz tone -> recovers ~full amplitude.
  assert(target_mags[0] > 10000.0f);
  // The same bin should show far less energy for an unrelated 1kHz tone.
  assert(target_mags[0] > 10.0f * control_mags[0]);
  printf("goertzel selectivity: target[0]=%.1f control[0]=%.1f (pass)\n", target_mags[0], control_mags[0]);
}

// Feeds `num_full_cycles` worth of a clean T3 pattern (3 beeps @ 500ms on/off + 1500ms
// pause), back to back. Note: T3Detector only confirms cycle K once it sees cycle K+1's
// first beep start (that's what proves the preceding pause was the right length), so
// `num_full_cycles` beep-groups yields (num_full_cycles - 1) *confirmed* cycles.
void run_t3_pattern(T3Detector &d, uint32_t &t, int num_full_cycles) {
  for (int c = 0; c < num_full_cycles; c++) {
    d.feed(true, t);
    t += 500;
    d.feed(false, t);
    t += 500;
    d.feed(true, t);
    t += 500;
    d.feed(false, t);
    t += 500;
    d.feed(true, t);
    t += 500;
    d.feed(false, t);
    t += 1500;
  }
}

void test_t3_three_beep_groups_detected() {
  T3Detector d;
  uint32_t t = 0;
  run_t3_pattern(d, t, 3);  // 3 beep-groups = 2 confirmed cycles
  assert(d.is_detected());
  printf("t3: 3 clean beep-groups -> detected (pass)\n");
}

void test_t3_two_beep_groups_not_yet_detected() {
  T3Detector d;
  uint32_t t = 0;
  run_t3_pattern(d, t, 2);  // 2 beep-groups = only 1 confirmed cycle
  assert(!d.is_detected());
  printf("t3: 2 clean beep-groups -> not yet detected (pass)\n");
}

void test_t3_mistimed_gap_resets_then_recovers() {
  T3Detector d;
  uint32_t t = 0;

  // Beep 1, then a badly mistimed gap (2000ms instead of ~500ms) before beep 2.
  d.feed(true, t);
  t += 500;
  d.feed(false, t);  // beep 1 done, beeps_in_cycle=1, IN_GAP
  t += 2000;          // way outside the +/-150ms tolerance for a 500ms gap
  d.feed(true, t);    // reset_() fires; this same edge starts a fresh beep 1 instead
  assert(!d.is_detected());

  // Finish that beep-group cleanly (2 more beeps), then continue with clean groups.
  t += 500;
  d.feed(false, t);  // fresh beep 1 done, beeps_in_cycle=1, IN_GAP
  t += 500;
  d.feed(true, t);  // beep 2 start
  t += 500;
  d.feed(false, t);  // beep 2 done, beeps_in_cycle=2, IN_GAP
  t += 500;
  d.feed(true, t);  // beep 3 start
  t += 500;
  d.feed(false, t);  // beep 3 done, beeps_in_cycle=3, IN_PAUSE
  t += 1500;
  run_t3_pattern(d, t, 2);  // 2 more clean beep-groups -> confirms 2 cycles from here
  assert(d.is_detected());
  printf("t3: mistimed gap resets, detector recovers on the next clean pattern (pass)\n");
}

}  // namespace

int main() {
  test_goertzel_selectivity();
  test_t3_three_beep_groups_detected();
  test_t3_two_beep_groups_not_yet_detected();
  test_t3_mistimed_gap_resets_then_recovers();
  printf("all core tests passed\n");
  return 0;
}
