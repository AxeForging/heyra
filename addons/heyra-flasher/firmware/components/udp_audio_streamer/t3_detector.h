#pragma once
#include <cstdint>

// Zero ESP-IDF/Arduino includes — host-testable.
namespace heyra::core {

// Detects the smoke-alarm T3 pattern: 3 beeps (~0.5s on/off) + 1.5s pause, repeating,
// requiring >=2 full cycles before firing. Driven by caller-supplied booleans + timestamps
// (typically one feed() per Goertzel window, i.e. every 64ms) — no wall-clock coupling.
class T3Detector {
 public:
  void feed(bool beep_present, uint32_t now_ms);
  bool is_detected() const { return detected_; }

 private:
  enum class State { IDLE, IN_BEEP, IN_GAP, IN_PAUSE };

  void reset_();

  State state_{State::IDLE};
  bool prev_beep_{false};
  uint8_t beeps_in_cycle_{0};
  uint8_t cycles_confirmed_{0};
  uint32_t edge_ms_{0};
  uint32_t last_beep_ms_{0};
  bool detected_{false};

  static constexpr uint32_t BEEP_MS = 500;
  static constexpr uint32_t GAP_MS = 500;
  static constexpr uint32_t PAUSE_MS = 1500;
  static constexpr uint32_t BEEP_TOL_MS = 200;
  static constexpr uint32_t GAP_TOL_MS = 200;
  // Real-hardware measurement (2026-07-30, ATOM Echo + computer speakers) showed the
  // silence-to-next-beep transition running ~300-500ms longer than the nominal 1.5s pause,
  // with run-to-run jitter -- likely playback-chain wake latency after a stretch of
  // silence, not a beep/gap issue (those measured spot-on within +/-50ms). This is a
  // property of the ad hoc computer-speaker test rig, not necessarily of a real alarm or
  // phone speaker; 700ms gives headroom against the observed jitter for now. Revisit
  // against a genuine smoke-alarm T3 recording during Phase 4 calibration.
  static constexpr uint32_t PAUSE_TOL_MS = 700;
  static constexpr uint8_t BEEPS_PER_CYCLE = 3;
  static constexpr uint8_t CYCLES_REQUIRED = 2;
  // If already detected and no beep for this long, auto-clear; re-arming requires the
  // full 2-cycle proof again (deliberately simple: no separate confirmed-vs-ringing latch).
  static constexpr uint32_t SILENCE_TIMEOUT_MS = 6000;
};

}  // namespace heyra::core
