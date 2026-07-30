#include "udp_audio_streamer.h"

#include <cstring>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#include "tone_synth.h"

namespace esphome::udp_audio_streamer {

static const char *const TAG = "udp_audio_streamer";

void UDPAudioStreamer::setup() {
  socket_ = socket::socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
  if (socket_ == nullptr) {
    ESP_LOGE(TAG, "Could not create UDP socket");
    this->mark_failed();
    return;
  }
  socket_->setblocking(false);
  socket::set_sockaddr(&dest_addr_, sizeof(dest_addr_), server_ip_.c_str(), server_port_);

  mic_->add_data_callback([this](const std::vector<uint8_t> &data) { this->on_mic_data_(data); });
  // Mic runs continuously -- Goertzel needs it regardless of the streaming switch's state.
  // The only time it genuinely stops is during play_alert's half-duplex sequencing below.
  mic_->start();
}

void UDPAudioStreamer::dump_config() {
  ESP_LOGCONFIG(TAG,
                "UDP Audio Streamer:\n"
                "  Unit ID: %u\n"
                "  Server: %s:%u",
                unit_id_, server_ip_.c_str(), server_port_);
}

void UDPAudioStreamer::loop() { this->tick_alert_(); }

void UDPAudioStreamer::on_mic_data_(const std::vector<uint8_t> &data) {
  const int16_t *samples = reinterpret_cast<const int16_t *>(data.data());
  size_t n = data.size() / 2;

  for (size_t i = 0; i < n; i++) {
    float mags[core::GOERTZEL_NUM_BINS];
    if (filter_bank_.process_sample(samples[i], mags)) {
      bool beep = core::is_beep_present(mags);
      t3_.feed(beep, millis());
      smoke_alarm_detected_.store(t3_.is_detected());
    }
  }

  if (streaming_enabled_.load()) {
    // The mic delivers fixed 512-byte (256-sample) chunks, so this never overruns
    // PAYLOAD_BYTES (1024) -- two chunks fill exactly one packet.
    memcpy(packet_.payload + packet_fill_, data.data(), data.size());
    packet_fill_ += data.size();
    if (packet_fill_ >= core::PAYLOAD_BYTES) {
      send_packet_(core::PAYLOAD_BYTES, 0);
      packet_fill_ = 0;
    }
  } else {
    uint32_t now = millis();
    if (now - last_keepalive_ms_ >= 1000) {
      send_packet_(0, core::FLAG_PAUSED);
      last_keepalive_ms_ = now;
    }
  }
}

void UDPAudioStreamer::send_packet_(size_t payload_len, uint8_t flags) {
  packet_.header.magic = core::MAGIC;
  packet_.header.unit_id = unit_id_;
  packet_.header.flags = flags;
  packet_.header.seq = seq_++;
  packet_.header.timestamp_ms = millis();

  size_t send_len = sizeof(core::PacketHeader) + payload_len;
  // Non-blocking socket (setblocking(false) in setup()): a dropped/short send here just
  // means this packet is lost -- the server must tolerate seq gaps, never block the mic task.
  socket_->sendto(&packet_, send_len, 0, &dest_addr_, sizeof(dest_addr_));
}

void UDPAudioStreamer::play_alert(int32_t tone_id) {
  if (phase_ != AlertPhase::IDLE) {
    ESP_LOGW(TAG, "play_alert(%d) ignored, already playing an alert", static_cast<int>(tone_id));
    return;
  }
  pending_tone_ = tone_id;
  mic_->stop();
  phase_ = AlertPhase::STOPPING_MIC;
  phase_deadline_ms_ = millis() + 3000;
}

void UDPAudioStreamer::tick_alert_() {
  switch (phase_) {
    case AlertPhase::IDLE:
      return;

    case AlertPhase::STOPPING_MIC:
      if (mic_->is_stopped()) {
        speaker_->start();
        phase_ = AlertPhase::STARTING_SPK;
      }
      break;

    case AlertPhase::STARTING_SPK:
      if (speaker_->is_running()) {
        tone_samples_sent_ = 0;
        tone_samples_total_ = core::tone_sample_count(pending_tone_);
        phase_ = AlertPhase::PLAYING;
      }
      break;

    case AlertPhase::PLAYING: {
      // Rendered chunk-by-chunk, never pre-rendered into one multi-KB buffer -- there's
      // no PSRAM headroom for that on this part.
      int16_t chunk[256];
      size_t n = core::render_tone_chunk(pending_tone_, tone_samples_sent_, chunk, 256);
      speaker_->play(reinterpret_cast<uint8_t *>(chunk), n * sizeof(int16_t));
      tone_samples_sent_ += n;
      if (tone_samples_sent_ >= tone_samples_total_) {
        speaker_->finish();
        phase_ = AlertPhase::STOPPING_SPK;
      }
      break;
    }

    case AlertPhase::STOPPING_SPK:
      if (speaker_->is_stopped()) {
        mic_->start();
        phase_ = AlertPhase::IDLE;
      }
      break;
  }

  if (phase_ != AlertPhase::IDLE && millis() > phase_deadline_ms_) {
    ESP_LOGE(TAG, "play_alert stuck in phase %d, forcing mic restart", static_cast<int>(phase_));
    mic_->start();
    phase_ = AlertPhase::IDLE;
  }
}

}  // namespace esphome::udp_audio_streamer
