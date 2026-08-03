#include "udp_audio_streamer.h"

#include <cstring>
#include <netdb.h>
#include <arpa/inet.h>

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#include "tone_synth.h"

namespace esphome::udp_audio_streamer {

static const char *const TAG = "udp_audio_streamer";

namespace {
// server_host_ can be a literal IP or an mDNS ".local" hostname -- set_sockaddr() below
// only accepts a literal IP (inet_pton internally), so this resolves once, up front.
// Blocking (getaddrinfo) -- callers MUST run this off the main/App task (see
// UDPAudioStreamer::resolve_task_). A boot-time mDNS lookup can take far longer than
// ESPHome's 5s task-watchdog window if the network isn't up yet, and running it inline in
// setup() used to crash the device (task_wdt trigger -> reboot -> ESPHome safe mode).
bool resolve_host_(const std::string &host, std::string *out_ip) {
  struct addrinfo hints {};
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_DGRAM;
  struct addrinfo *result = nullptr;
  if (getaddrinfo(host.c_str(), nullptr, &hints, &result) != 0 || result == nullptr) {
    return false;
  }
  char buf[INET_ADDRSTRLEN];
  auto *addr_in = reinterpret_cast<struct sockaddr_in *>(result->ai_addr);
  inet_ntop(AF_INET, &addr_in->sin_addr, buf, sizeof(buf));
  *out_ip = buf;
  freeaddrinfo(result);
  return true;
}
}  // namespace

// Runs on its own FreeRTOS task (spawned by setup()), never on the watchdog-monitored
// main/App task. Retries forever, however long DNS/mDNS takes, then publishes the result
// via server_resolved_ (std::atomic -- also what makes the dest_addr_ write below visible
// to the mic task in send_packet_()) and deletes itself.
void UDPAudioStreamer::resolve_task_(void *arg) {
  auto *self = static_cast<UDPAudioStreamer *>(arg);
  std::string ip;
  while (!resolve_host_(self->server_host_, &ip)) {
    vTaskDelay(pdMS_TO_TICKS(2000));
  }
  socket::set_sockaddr(&self->dest_addr_, sizeof(self->dest_addr_), ip.c_str(), self->server_port_);
  ESP_LOGI(TAG, "Resolved server host '%s' -> %s", self->server_host_.c_str(), ip.c_str());
  self->server_resolved_.store(true);
  vTaskDelete(nullptr);
}

void UDPAudioStreamer::setup() {
  socket_ = socket::socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
  if (socket_ == nullptr) {
    ESP_LOGE(TAG, "Could not create UDP socket");
    this->mark_failed();
    return;
  }
  socket_->setblocking(false);

  // Small stack (mDNS/DNS resolution + a std::string, no audio processing), low priority
  // -- this task only exists to keep a blocking network call off the main App task.
  xTaskCreate(&UDPAudioStreamer::resolve_task_, "heyra_resolve", 4096, this, 1, nullptr);

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
                unit_id_, server_host_.c_str(), server_port_);
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
  if (!server_resolved_) {
    return;  // nothing to send to yet -- setup()'s resolve retry is still in flight
  }
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
