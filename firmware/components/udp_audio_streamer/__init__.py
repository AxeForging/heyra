import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import microphone, speaker
from esphome.const import CONF_ID

CODEOWNERS = ["@heyra"]
DEPENDENCIES = ["microphone", "speaker"]

CONF_MICROPHONE_ID = "microphone_id"
CONF_SPEAKER_ID = "speaker_id"
CONF_SERVER_HOST = "server_host"
CONF_SERVER_PORT = "server_port"

udp_audio_streamer_ns = cg.esphome_ns.namespace("udp_audio_streamer")
UDPAudioStreamer = udp_audio_streamer_ns.class_("UDPAudioStreamer", cg.Component)

# unit_id (matches the packet's u8 field, 1..255) is no longer a compile-time value here --
# one shared image serves every physical unit, so unit_id is set at runtime via the
# number: entity in common.yaml (id(streamer).set_unit_id()), not baked in per build.
CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(UDPAudioStreamer),
        cv.Required(CONF_MICROPHONE_ID): cv.use_id(microphone.Microphone),
        cv.Required(CONF_SPEAKER_ID): cv.use_id(speaker.Speaker),
        # Literal IP or an mDNS ".local" hostname -- resolved once at setup() (see
        # udp_audio_streamer.cpp), not by ESPHome's own compile-time codegen.
        cv.Required(CONF_SERVER_HOST): cv.string,
        cv.Required(CONF_SERVER_PORT): cv.port,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    cg.add(var.set_server_host(config[CONF_SERVER_HOST]))
    cg.add(var.set_server_port(config[CONF_SERVER_PORT]))

    mic = await cg.get_variable(config[CONF_MICROPHONE_ID])
    cg.add(var.set_microphone(mic))
    spk = await cg.get_variable(config[CONF_SPEAKER_ID])
    cg.add(var.set_speaker(spk))
