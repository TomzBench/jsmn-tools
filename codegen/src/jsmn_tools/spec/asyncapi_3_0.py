from __future__ import annotations

from enum import StrEnum

from jsmn_tools.node import (
    _NO_BHV,
    NAMED,
    Behavior,
    DraftKeys,
    Location,
    MapNode,
    ObjectNode,
    data,
)

from .json_schema import map_schema_enter, schema_enter
from .rules import Verdict


class AsyncAPIKind(StrEnum):
    # Object nodes
    ROOT = "asyncapi"
    COMPONENTS = "components"
    CHANNEL = "channel"
    OPERATION = "operation"
    MESSAGE = "message"
    MESSAGE_TRAIT = "message_trait"
    OPERATION_TRAIT = "operation_trait"
    SERVER = "server"
    SERVER_VAR = "server_var"
    REPLY = "reply"
    PARAMETER = "parameter"
    # Map nodes
    MAP_SERVER = "map_server"
    MAP_CHANNEL = "map_channel"
    MAP_OPERATION = "map_operation"
    MAP_MESSAGE = "map_message"
    MAP_MESSAGE_TRAIT = "map_message_trait"
    MAP_OPERATION_TRAIT = "map_operation_trait"
    MAP_PARAMETER = "map_parameter"
    MAP_SERVER_VAR = "map_server_var"
    MAP_REPLY = "map_reply"


# --- Object nodes ---
obj_root: ObjectNode[DraftKeys[AsyncApi30Keys]] = ObjectNode(AsyncAPIKind.ROOT)
obj_components = ObjectNode(AsyncAPIKind.COMPONENTS)
obj_channel = ObjectNode(AsyncAPIKind.CHANNEL)
obj_operation = ObjectNode(AsyncAPIKind.OPERATION)
obj_message = ObjectNode(AsyncAPIKind.MESSAGE)
obj_message_trait = ObjectNode(AsyncAPIKind.MESSAGE_TRAIT)
obj_operation_trait = ObjectNode(AsyncAPIKind.OPERATION_TRAIT)
obj_server = ObjectNode(AsyncAPIKind.SERVER)
obj_server_var = ObjectNode(AsyncAPIKind.SERVER_VAR)
obj_reply = ObjectNode(AsyncAPIKind.REPLY)
obj_parameter = ObjectNode(AsyncAPIKind.PARAMETER)

# --- Map nodes ---
map_server = MapNode(AsyncAPIKind.MAP_SERVER)
map_channel = MapNode(AsyncAPIKind.MAP_CHANNEL)
map_operation = MapNode(AsyncAPIKind.MAP_OPERATION)
map_message = MapNode(AsyncAPIKind.MAP_MESSAGE)
map_message_trait = MapNode(AsyncAPIKind.MAP_MESSAGE_TRAIT)
map_operation_trait = MapNode(AsyncAPIKind.MAP_OPERATION_TRAIT)
map_parameter = MapNode(AsyncAPIKind.MAP_PARAMETER)
map_server_var = MapNode(AsyncAPIKind.MAP_SERVER_VAR)
map_reply = MapNode(AsyncAPIKind.MAP_REPLY)


# fmt: off
obj_root.configure(table={
    "servers":          (map_server, NAMED),
    "channels":         (map_channel, NAMED),
    "operations":       (map_operation, NAMED),
    "components":       (obj_components, _NO_BHV),
})

obj_components.configure(table={
    "schemas":          (map_schema_enter, NAMED),
    "servers":          (map_server, NAMED),
    "channels":         (map_channel, NAMED),
    "operations":       (map_operation, NAMED),
    "messages":         (map_message, NAMED),
    "parameters":       (map_parameter, NAMED),
    "operationTraits":  (map_operation_trait, NAMED),
    "messageTraits":    (map_message_trait, NAMED),
    "serverVariables":  (map_server_var, NAMED),
    "replies":          (map_reply, NAMED),
})

obj_channel.configure(table={
    "messages":         (map_message, _NO_BHV),
    "parameters":       (map_parameter, _NO_BHV),
})

obj_operation.configure(table={
    "reply":            (obj_reply, _NO_BHV),
})

obj_message.configure(table={
    "payload":          (schema_enter, _NO_BHV),
    "headers":          (schema_enter, _NO_BHV),
})

obj_message_trait.configure(table={
    "headers":          (schema_enter, _NO_BHV),
})

obj_operation_trait.configure(table={})

obj_server.configure(table={
    "variables":        (map_server_var, _NO_BHV),
})

obj_server_var.configure(table={
    "enum":             (data, Behavior(identity=str)),
})

obj_reply.configure(table={})

obj_parameter.configure(table={
    "enum":             (data, Behavior(identity=str)),
})

# --- Map node configuration ---
map_server.configure(child=obj_server)
map_channel.configure(child=obj_channel)
map_operation.configure(child=obj_operation)
map_message.configure(child=obj_message)
map_message_trait.configure(child=obj_message_trait)
map_operation_trait.configure(child=obj_operation_trait)
map_parameter.configure(child=obj_parameter)
map_server_var.configure(child=obj_server_var)
map_reply.configure(child=obj_reply)
# fmt: on

type AsyncApi30Keys = DraftKeys[AsyncAPIKind]


def conflict_rules(path: Location) -> Verdict:
    """Per-document metadata is the first spec's; anything else is an error.

    ``info`` and root extensions describe one input document, not the
    joined API, so two inputs disagreeing on them says nothing.
    """
    match path:
        case ("info", *_):
            return Verdict.IGNORE
        case (str(key), *_) if key.startswith("x-"):
            return Verdict.IGNORE
        case _:
            return Verdict.ERROR
