#pragma once

#include <atomic>
#include <memory>
#include <string>

#include "esphome/core/component.h"
#include "esphome/components/microphone/microphone.h"
#include "esphome/components/speaker/speaker.h"
#include "esphome/components/socket/socket.h"

#include "goertzel.h"
#include "packet.h"
#include "t3_detector.h"

namespace esphome::udp_audio_streamer {

namespace core = heyra::core;  // alias so core::X below resolves to heyra::core::X

class UDPAudioStreamer : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  // Called at boot from on_boot: (restored value) and live from the Unit ID number
  // entity's set_action -- no longer a compile-time constant, see __init__.py.
  void set_unit_id(uint8_t id) { unit_id_ = id; }
  // Literal IP or an mDNS ".local" hostname -- resolved to a literal IP once in setup(),
  // see resolve_host_() in the .cpp.
  void set_server_host(const std::string &host) { server_host_ = host; }
  void set_server_port(uint16_t port) { server_port_ = port; }
  void set_microphone(microphone::Microphone *mic) { mic_ = mic; }
  void set_speaker(speaker::Speaker *spk) { speaker_ = spk; }

  // Called from switch: platform: template (main-loop thread).
  void set_streaming(bool enabled) { streaming_enabled_.store(enabled); }
  bool get_streaming() const { return streaming_enabled_.load(); }

  // Called from binary_sensor: platform: template, polled (main-loop thread).
  bool is_smoke_alarm_detected() const { return smoke_alarm_detected_.load(); }

  // Called from the `play_alert` api: actions: entry (main-loop thread).
  void play_alert(int32_t tone_id);

 protected:
  // *** Runs on the microphone component's own FreeRTOS task, NOT the main loop task. ***
  void on_mic_data_(const std::vector<uint8_t> &data);
  void send_packet_(size_t payload_len, uint8_t flags);
  void tick_alert_();

  microphone::Microphone *mic_{nullptr};
  speaker::Speaker *speaker_{nullptr};
  uint8_t unit_id_{0};
  std::string server_host_;
  uint16_t server_port_{0};
  std::unique_ptr<socket::Socket> socket_;
  struct sockaddr dest_addr_ {};
  // False until server_host_ resolves -- send_packet_() no-ops until then. A boot-time
  // DNS/mDNS race against the network coming up is expected, not a hard failure; setup()
  // retries on an interval until this flips true.
  bool server_resolved_{false};

  std::atomic<bool> streaming_enabled_{true};
  std::atomic<bool> smoke_alarm_detected_{false};

  // Mic-task-thread-owned only (single writer -- no lock needed).
  core::Packet packet_{};
  size_t packet_fill_{0};
  uint16_t seq_{0};
  core::GoertzelFilterBank filter_bank_;
  core::T3Detector t3_;
  uint32_t last_keepalive_ms_{0};

  // Main-loop-thread-owned only.
  enum class AlertPhase { IDLE, STOPPING_MIC, STARTING_SPK, PLAYING, STOPPING_SPK };
  AlertPhase phase_{AlertPhase::IDLE};
  int32_t pending_tone_{0};
  size_t tone_samples_sent_{0};
  size_t tone_samples_total_{0};
  uint32_t phase_deadline_ms_{0};
};

}  // namespace esphome::udp_audio_streamer
