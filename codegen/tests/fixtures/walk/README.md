# Walk fixtures

Specs for `test_walk_openapi_3_1.py` and `test_walk_asyncapi_3_0.py`.

| File                       | Test                   | Shows                                                    |
| -------------------------- | ---------------------- | -------------------------------------------------------- |
| `paths.yaml`               | `test_walk_dicts`, `test_walk_lists`, `test_walk_scalars` | The walk yields dicts, lists and leaf scalars |
| `paths.yaml`, `components.yaml` | `test_walk_multi_spec` | Walking several specs yields the steps of each      |
| `lists.yaml`               | `test_walk_list_kinds` | A list is a place of its own in the draft (see below)    |
| `asyncapi_*.yaml`          | `test_walk_asyncapi_3_0.py` | The same walk over the AsyncAPI draft               |

## `lists.yaml`

A list has its own node in the draft, as a map does: the list is one kind of
thing and its items another. An index is a key like any other, so the walk
finds an item's place the way it finds a dict value's: by asking the list's
node.

The fixture holds one of each list the drafts give a node, and the test checks
the kind of the list and of its items:

| List                      | Kind of the list | Kind of an item |
| ------------------------- | ---------------- | --------------- |
| `servers`                 | `list_server`    | `server`        |
| `security`                | `list_security`  | `map_scope`     |
| `parameters`              | `list_parameter` | `parameter`     |
| `anyOf`, `prefixItems`    | `list_schema`    | `schema`        |
| `enum` (and a list in it) | `data`           | `data`          |

`enum` is data. Data is a trap: everything under it is data, a list and its
items included. The server item is checked one step further (`variables` is a
`map_server_var`) to show the walk carries on from an item's own node.
