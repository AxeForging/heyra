import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import microphone, speaker
from esphome.const import CONF_ID

CODEOWNERS = ["@heyra"]
DEPENDENCIES = ["microphone", "speaker"]

CONF_UNIT_ID = "unit_id"
CONF_MICROPHONE_ID = "microphone_id"
CONF_SPEAKER_ID = "speaker_id"
CONF_SERVER_IP = "server_ip"
CONF_SERVER_PORT = "server_port"

udp_audio_streamer_ns = cg.esphome_ns.namespace("udp_audio_streamer")
UDPAudioStreamer = udp_audio_streamer_ns.class_("UDPAudioStreamer", cg.Component)

# unit_id matches the packet's u8 field (1..255) -- not capped to any particular fleet size.
CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(UDPAudioStreamer),
        cv.Required(CONF_UNIT_ID): cv.int_range(min=1, max=255),
        cv.Required(CONF_MICROPHONE_ID): cv.use_id(microphone.Microphone),
        cv.Required(CONF_SPEAKER_ID): cv.use_id(speaker.Speaker),
        cv.Required(CONF_SERVER_IP): cv.string,
        cv.Required(CONF_SERVER_PORT): cv.port,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    cg.add(var.set_unit_id(config[CONF_UNIT_ID]))
    cg.add(var.set_server_ip(config[CONF_SERVER_IP]))
    cg.add(var.set_server_port(config[CONF_SERVER_PORT]))

    mic = await cg.get_variable(config[CONF_MICROPHONE_ID])
    cg.add(var.set_microphone(mic))
    spk = await cg.get_variable(config[CONF_SPEAKER_ID])
    cg.add(var.set_speaker(spk))
