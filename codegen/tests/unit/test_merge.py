from jsmn_tools.node import Behavior, Location, data
from jsmn_tools.walk import merge


def test_conflict_keeps_destination() -> None:
    """A conflict is reported and the destination kept; the arguments are
    left as they were."""
    dst = {"port": {"speed": 1}, "only": {}}
    src = {"port": {"speed": 2}, "new": {}}
    (value, conflicts) = merge(dst, src, (data, Behavior(identity=str)))
    assert value == {"port": {"speed": 1}, "only": {}, "new": {}}
    assert [c.location for c in conflicts] == [Location(("port",))]
    assert value["new"] is not src["new"]
    assert dst == {"port": {"speed": 1}, "only": {}}
    assert src == {"port": {"speed": 2}, "new": {}}


def test_dict_identity_pairs_keys() -> None:
    """An identified dict pairs entries by identity(key); the first
    spelling of the key is the one kept."""
    folded = Behavior(identity=str.lower)
    (value, conflicts) = merge({"Port": 1}, {"port": 2, "x": 3}, (data, folded))
    assert value == {"Port": 1, "x": 3}
    assert [c.location for c in conflicts] == [Location(("Port",))]
