#include "t3_detector.h"

namespace heyra::core {

namespace {
bool within_tolerance(uint32_t elapsed_ms, uint32_t expected_ms, uint32_t tol_ms) {
  return elapsed_ms + tol_ms >= expected_ms && elapsed_ms <= expected_ms + tol_ms;
}
}  // namespace

void T3Detector::reset_() {
  state_ = State::IDLE;
  beeps_in_cycle_ = 0;
  cycles_confirmed_ = 0;
  detected_ = false;
}

void T3Detector::feed(bool beep_present, uint32_t now_ms) {
  if (beep_present) {
    last_beep_ms_ = now_ms;
  }
  if (detected_ && (now_ms - last_beep_ms_) > SILENCE_TIMEOUT_MS) {
    reset_();
  }

  bool rising = beep_present && !prev_beep_;
  bool falling = !beep_present && prev_beep_;
  prev_beep_ = beep_present;

  switch (state_) {
    case State::IDLE:
      if (rising) {
        state_ = State::IN_BEEP;
        edge_ms_ = now_ms;
      }
      break;

    case State::IN_BEEP:
      if (falling) {
        if (!within_tolerance(now_ms - edge_ms_, BEEP_MS, BEEP_TOL_MS)) {
          reset_();
          break;
        }
        beeps_in_cycle_++;
        edge_ms_ = now_ms;
        state_ = (beeps_in_cycle_ < BEEPS_PER_CYCLE) ? State::IN_GAP : State::IN_PAUSE;
      }
      break;

    case State::IN_GAP:
      if (rising) {
        if (!within_tolerance(now_ms - edge_ms_, GAP_MS, GAP_TOL_MS)) {
          reset_();
          state_ = State::IN_BEEP;  // this edge can still start a fresh attempt
          edge_ms_ = now_ms;
          break;
        }
        edge_ms_ = now_ms;
        state_ = State::IN_BEEP;
      }
      break;

    case State::IN_PAUSE:
      if (rising) {
        if (!within_tolerance(now_ms - edge_ms_, PAUSE_MS, PAUSE_TOL_MS)) {
          reset_();
          state_ = State::IN_BEEP;  // this edge can still start a fresh attempt
          edge_ms_ = now_ms;
          break;
        }
        cycles_confirmed_++;
        beeps_in_cycle_ = 0;  // this rising edge starts beep 1 of the new cycle; IN_BEEP's
                               // falling-edge handler is what counts it once it completes
        edge_ms_ = now_ms;
        state_ = State::IN_BEEP;
        if (cycles_confirmed_ >= CYCLES_REQUIRED) {
          detected_ = true;
        }
      }
      break;
  }
}

}  // namespace heyra::core
