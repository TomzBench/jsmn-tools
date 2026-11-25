# Join test fixtures

OpenAPI 3.1 fragments for the two steps that turn many specs into one document:
`normalize` (rewrite one spec into its canonical form) and `join` (merge the
normalized specs and report where they disagree). Used by
`test_join_openapi_3_1.py` and `test_normalize_openapi_3_1.py`.

Most fixtures come as an `_a` / `_b` pair: the same API written twice, either
in a different order or with a real disagreement. The tests give each spec an
`$id` (`spec:0`, `spec:1`, ...) and normalize it before joining, as a caller
must.

## The rules under test

A draft (`spec/openapi_3_1.py`, `spec/json_schema.py`) says what each place in
a spec *is*, and may give the collection found there an **identity**:

| Collection       | With an identity                               | Without                 |
| ---------------- | ---------------------------------------------- | ----------------------- |
| list (normalize) | a set: sorted by identity                      | ordered: left as is     |
| list (join)      | items paired by identity, compared whole       | merged by position      |
| dict (join)      | entries are definitions, compared whole        | merged key by key       |

Two more rules decide how far a place reaches:

- **Data traps.** Under `default`, `example`, `const` or any `x-*` key the
  content is opaque data: nothing is sorted and a `$ref` is not a reference.
- **An identity stops at its list.** It describes the list it is declared on.
  The items keep the list's place in the draft, but not its identity.

## Normalize only

| File                | Test                                     | Shows                                                                                    |
| ------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------- |
| `refs.yaml`         | `test_normalize_refs`                    | A `$ref` into another document collapses to its `#/fragment`; local refs and refs inside data traps are untouched. `definitions` (the pre-2019-09 `$defs`) is a map of schemas, so a definition named `x-legacy` is a schema, not an extension. A property named `$ref` is a name, not a reference: its schema is normalized like any other |
| `nested_lists.yaml` | `test_normalize_nested_list_keeps_order` | A list inside a set keeps its order (see below)                                          |

### `nested_lists.yaml`

`enum` and `examples` are sets, so their members are sorted. A member may
itself be an array, and then its order is part of the value: `[3, 1, 2]` and
`[1, 2, 3]` are different enum members.

An identity describes the list it is given to, not the items in it: an item
gets its behavior from the list's node, as a dict value does. Normalize once
passed the list's identity down to its items, so an array-valued member was
sorted too and `[3, 1, 2]` became `[1, 2, 3]`, silently changing the schema. The fixture holds one set of each
kind with array members written out of order; the test checks that the outer
list is sorted and the inner ones are not.

## Sets: order does not matter

Each pair is the same spec with its sets written in a different order. The join
must report no conflict and produce the sorted form.

| Files               | Test                        | Sets covered                                                                 |
| ------------------- | --------------------------- | ---------------------------------------------------------------------------- |
| `schema_sets_*`     | `test_join_schema_sets`     | `required`, `type`, `enum`, `oneOf`                                           |
| `openapi_sets_*`    | `test_join_openapi_sets`    | operation `tags`, `parameters` (by `in`, `name`), `security`, scopes, server variable `enum` |
| `schema_dispatch_*` | `test_join_schema_dispatch` | `dependentRequired` values, `enum` / `examples` under `$defs`; arrays under `default` and `x-meta` are data traps and stay unsorted |

## Ordered lists: order does matter

| Files       | Test                | Shows                                                                                              |
| ----------- | ------------------- | -------------------------------------------------------------------------------------------------- |
| `ordered_*` | `test_join_ordered` | `servers`, `prefixItems` and root `tags` have no identity: the reordered pair stays different and the join conflicts |

## Merging and conflicts

| Files                      | Test                             | Shows                                                                                         |
| -------------------------- | -------------------------------- | --------------------------------------------------------------------------------------------- |
| `merge_union_*`            | `test_join_union`                | `components.schemas` is a map of definitions: `alpha` differs, so one conflict at `alpha` and the first spec's is kept whole (not merged); `beta` is new and copied in |
| `path_fragments_a` + `_b`  | `test_join_path_fragments`       | A path item is merged key by key: specs may each add methods and parameters to one path       |
| `path_fragments_a` + `_c`  | `test_join_path_method_conflict` | One method defined twice conflicts at the field that differs (`responses`); the first is kept |
| `merge_conflict_*`         | `test_join_conflict`             | Three conflicts: `info.title`, `info.version`, and a parameter with the same (`in`, `name`) but a different schema, reported at the `parameters` list because an item has no pointer of its own |

`test_join_same_definition_twice` and `test_join_security_schemes` build their
specs inline and use no fixture.
