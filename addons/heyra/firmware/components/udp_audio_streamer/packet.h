#pragma once
#include <cstdint>
#include <cstddef>

// Zero ESP-IDF/Arduino includes — host-testable. See CLAUDE.md for the frozen wire contract.
namespace heyra::core {

static constexpr uint32_t MAGIC = 0x41544D45;                  // "ATME"
static constexpr size_t PAYLOAD_SAMPLES = 512;                 // 32ms @ 16kHz
static constexpr size_t PAYLOAD_BYTES = PAYLOAD_SAMPLES * 2;   // 1024

enum PacketFlags : uint8_t { FLAG_PAUSED = 0x01 };

// ESP32 is little-endian natively, so a raw memcpy of this struct onto the wire already
// matches the spec's little-endian wire format — no htonl/byteswap needed.
struct __attribute__((packed)) PacketHeader {
  uint32_t magic;
  uint8_t unit_id;
  uint8_t flags;
  uint16_t seq;
  uint32_t timestamp_ms;
};
static_assert(sizeof(PacketHeader) == 12, "header must be exactly 12 bytes");

struct __attribute__((packed)) Packet {
  PacketHeader header;
  uint8_t payload[PAYLOAD_BYTES];
};
static_assert(sizeof(Packet) == 12 + PAYLOAD_BYTES, "no padding allowed");

}  // namespace heyra::core
