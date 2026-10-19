"""Deleting packaging: whole containers, and the link clean-up behind a grid delete.

What is inside a container is read from both tables and both are acted on, because
they can disagree at the edges: staging_product_logs (the links) knows containers
that hold nothing yet, while filling_product_logs has one row per unit. Deleting
only what one of them shows would leave the other pointing at something that is
gone.

A container that is left with nothing inside is removed too (its link to its own
parent), the same rule for a container delete and for deleting rows in the grid.
A link is never removed while any other row or link still sits inside it: display
and inner links are shared by every unit below them.
"""
import contextlib
from collections import defaultdict

import psycopg2
from psycopg2 import sql

from . import connection
from .hierarchy import (LEVELS, CONTAINER_LEVELS, STAGING_EDGE_TABLE,
                        ContainerDeleteError)
from .serial_state import _set_serials_inactive

# The links nest at most carton > inner > display > unit, so a chain longer than
# this is a loop in bad data, not a deeper hierarchy.
MAX_DEPTH = 4


def _edge_table(schema):
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STAGING_EDGE_TABLE))


def _flat_table(schema, table):
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


def _delete_links(cur, schema, ids):
    """Delete links by id. Returns the ids that were actually there and went."""
    if not ids:
        return []
    cur.execute(
        sql.SQL("DELETE FROM {edges} WHERE id = ANY(%s) RETURNING id").format(
            edges=_edge_table(schema)),
        (list(ids),),
    )
    return [row[0] for row in cur.fetchall()]


def _existing_links(cur, schema, ids):
    """Which of `ids` are links that really exist right now.

    The ids a saved row carries in its <level>_source_id are the only ones in a
    plan that were not just read out of the link table, and history leaves rows
    pointing at links that are already gone. Planning to delete one of those would
    make the plan's own count unreachable and abort the delete (see
    delete_container), so they are checked here and left out.
    """
    ids = sorted(ids)
    if not ids:
        return set()
    cur.execute(
        sql.SQL("SELECT id FROM {edges} WHERE id = ANY(%s)").format(edges=_edge_table(schema)),
        (ids,),
    )
    return {row[0] for row in cur.fetchall()}


def _children_tree(root_serial, root_level, links):
    """Everything inside a container as an indented list, each item after its parent.

    `links` are (id, serial_no, level, parent_serial_no, parent_level) rows. Every
    entry says how many items sit directly inside it, for an "n inside" label.
    """
    by_parent = defaultdict(set)
    for _link_id, serial, level, parent, parent_level in links:
        by_parent[(parent, parent_level)].add((serial, level))
    ordered = {
        key: sorted(items, key=lambda item: (str(item[0] or ""), item[1]))
        for key, items in by_parent.items()
    }

    out, seen = [], set()

    def walk(key, depth):
        for serial, level in ordered.get(key, ()):
            if (serial, level) in seen or depth > MAX_DEPTH:
                continue
            seen.add((serial, level))
            out.append({"serial_no": serial, "level": level, "depth": depth,
                        "children": len(ordered.get((serial, level), ()))})
            walk((serial, level), depth + 1)

    walk((root_serial, root_level), 1)
    return out


def _rows_as_links(level, serial_no, saved):
    """The contents a saved row knows about, shaped like links so they can be listed.

    The link table is not the only record of what is inside a container: a row in
    filling_product_logs names every level it sits in, and the two can disagree --
    a container whose links were never written, or were removed while its rows
    stayed, holds rows that no link points at. Listing only the links would then
    promise to delete N units and show nothing, which is exactly when a user most
    needs to see what is going.

    A level with no serial on the row is a gap, not a container: the level below
    it is listed under the nearest named one instead.
    """
    below = LEVELS[:LEVELS.index(level)]
    out = []
    for row in saved:
        parent, parent_level = serial_no, level
        for lower in reversed(below):  # outermost first, so each is under the last
            child = row.get(f"{lower}_serial_no")
            if child in (None, ""):
                continue
            child = str(child)
            out.append((None, child, lower, parent, parent_level))
            parent, parent_level = child, lower
    return out


def _prune_empty(cur, schema, table, candidates, gone_links, survivors, apply):
    """Find, and with `apply` delete, the link of every container left with nothing in it.

    `candidates` maps a container level to the serials that just lost something.
    A container is empty when no link outside `gone_links` names it as its parent
    and no row satisfying `survivors` -- (SQL condition on alias f, its params),
    which must exclude the rows being deleted -- sits in it. Levels are visited
    bottom-up because emptying a display can empty its inner; the parent of every
    link removed becomes a candidate in turn.

    Returns ([{"level", "serial_no"}, ...] emptied, sorted ids of the links removed).
    """
    condition, condition_params = survivors
    candidates = {level: set(serials) for level, serials in candidates.items()}
    gone = set(gone_links)
    emptied, removed = [], []

    for level in CONTAINER_LEVELS:
        serials = sorted(serial for serial in candidates.get(level, ()) if serial)
        if not serials:
            continue
        cur.execute(
            sql.SQL(
                "SELECT c.serial FROM unnest(%s::text[]) AS c(serial) "
                "WHERE NOT EXISTS (SELECT 1 FROM {edges} e "
                "WHERE e.parent_serial_no = c.serial "
                "AND e.parent_serial_label_code = %s AND e.id <> ALL(%s)) "
                "AND NOT EXISTS (SELECT 1 FROM {flat} f "
                "WHERE f.{column}::text = c.serial AND {condition})"
            ).format(
                edges=_edge_table(schema),
                flat=_flat_table(schema, table),
                column=sql.Identifier(f"{level}_serial_no"),
                condition=condition,
            ),
            (serials, level, sorted(gone), *condition_params),
        )
        empties = [row[0] for row in cur.fetchall()]
        if not empties:
            continue
        emptied.extend({"level": level, "serial_no": serial} for serial in empties)

        cur.execute(
            sql.SQL(
                "SELECT id, parent_serial_no, parent_serial_label_code FROM {edges} "
                "WHERE serial_label_code = %s AND serial_no = ANY(%s) AND id <> ALL(%s)"
            ).format(edges=_edge_table(schema)),
            (level, empties, sorted(gone)),
        )
        for link_id, parent, parent_level in cur.fetchall():
            removed.append(link_id)
            gone.add(link_id)
            if parent and parent_level in CONTAINER_LEVELS:
                candidates.setdefault(parent_level, set()).add(parent)

    removed.sort()
    if apply:
        _delete_links(cur, schema, removed)
    return emptied, removed


def remove_row_links(cur, schema, table, pk_column, rows, tag_name=None):
    """The link-table half of deleting `rows` from the grid.

    `rows` are the pre-delete rows of `table` (dicts) about to be deleted by the
    caller in the same transaction. Each row's own unit link is removed and its
    serial released, as it always was. A display or inner link goes too, but only
    when the whole batch leaves nothing inside that container; a sibling unit, or
    any other link naming it as parent, keeps the link alive. A container whose
    link goes this way has been deleted just as surely as one removed through
    delete_container, so its own serial is released as well.

    Returns the containers that were left empty and removed.
    """
    if not rows:
        return []
    _set_serials_inactive(cur, schema, (row.get("unit_serial_no") for row in rows), tag_name)

    unit_links = sorted({row["unit_source_id"] for row in rows
                         if row.get("unit_source_id") is not None})
    _delete_links(cur, schema, unit_links)

    candidates = defaultdict(set)
    for row in rows:
        for level in CONTAINER_LEVELS:
            serial = row.get(f"{level}_serial_no")
            if serial not in (None, ""):
                candidates[level].add(str(serial))

    survivors = (sql.SQL("f.{pk} <> ALL(%s)").format(pk=sql.Identifier(pk_column)),
                 ([row[pk_column] for row in rows],))
    emptied, _removed = _prune_empty(cur, schema, table, candidates, unit_links,
                                     survivors, apply=True)
    if emptied:
        _set_serials_inactive(cur, schema, (item["serial_no"] for item in emptied), tag_name)
    return emptied


def _require_container_level(level, serial_no):
    if level not in CONTAINER_LEVELS:
        raise ValueError(f"{level} is not a container level")
    if not serial_no:
        raise ValueError("Pick a container to delete")


def _plan(cur, schema, table, level, serial_no):
    """Read-only: everything deleting this container would touch.

    Raises ContainerDeleteError when the serial names no container, or names more
    than one (linked under two parents, or its rows spread over two): with no safe
    answer to "which one?", nothing is deleted.
    """
    edges = _edge_table(schema)
    column = f"{level}_serial_no"

    # 1. the container's own link to its parent
    cur.execute(
        sql.SQL("SELECT id, parent_serial_no, parent_serial_label_code FROM {edges} "
                "WHERE serial_no = %s AND serial_label_code = %s").format(edges=edges),
        (serial_no, level),
    )
    own = cur.fetchall()
    parents = {(parent, parent_level) for _link_id, parent, parent_level in own}
    if len(parents) > 1:
        raise ContainerDeleteError(
            f'{level} "{serial_no}" is linked under more than one parent '
            f'({", ".join(sorted(str(p) for p, _ in parents))}); '
            "refusing to guess which one to delete."
        )

    # 2. every link below it, however deep, from the link table
    cur.execute(
        sql.SQL(
            "WITH RECURSIVE inside AS ("
            "SELECT id, serial_no, serial_label_code, parent_serial_no, "
            "parent_serial_label_code, 1 AS depth FROM {edges} "
            "WHERE parent_serial_no = %s AND parent_serial_label_code = %s "
            "UNION ALL "
            "SELECT e.id, e.serial_no, e.serial_label_code, e.parent_serial_no, "
            "e.parent_serial_label_code, i.depth + 1 FROM {edges} e JOIN inside i "
            "ON e.parent_serial_no = i.serial_no "
            "AND e.parent_serial_label_code = i.serial_label_code "
            "WHERE i.depth < %s) "
            "SELECT id, serial_no, serial_label_code, parent_serial_no, "
            "parent_serial_label_code, depth FROM inside"
        ).format(edges=edges),
        (serial_no, level, MAX_DEPTH),
    )
    inside = {}
    for link_id, serial, link_level, parent, parent_level, _depth in cur.fetchall():
        inside.setdefault(link_id, (link_id, serial, link_level, parent, parent_level))

    # 3. the saved rows that sit in it
    cur.execute(
        sql.SQL("SELECT * FROM {flat} WHERE {column}::text = %s").format(
            flat=_flat_table(schema, table), column=sql.Identifier(column)),
        (serial_no,),
    )
    names = [description[0] for description in cur.description]
    saved = [dict(zip(names, values)) for values in cur.fetchall()]

    above = LEVELS[LEVELS.index(level) + 1:]
    for ancestor in above:
        seen = {row.get(f"{ancestor}_serial_no") for row in saved} - {None, ""}
        if len(seen) > 1:
            raise ContainerDeleteError(
                f'The saved rows of {level} "{serial_no}" sit in more than one {ancestor} '
                f'({", ".join(sorted(str(s) for s in seen))}); '
                "refusing to guess which one to delete."
            )
    if not (own or inside or saved):
        raise ContainerDeleteError(f'No {level} named "{serial_no}" exists.')

    # Links to remove: its own, everything below it, and whatever the rows point at.
    # The first two were just read from the link table; the third is checked,
    # because a row can still name a link that no longer exists.
    links = {link_id for link_id, _parent, _parent_level in own} | set(inside)
    named_by_rows = set()
    for row in saved:
        for lower in LEVELS[:LEVELS.index(level) + 1]:
            link = row.get(f"{lower}_source_id")
            if link is not None:
                named_by_rows.add(link)
    unchecked = named_by_rows - links
    orphans = sorted(unchecked - _existing_links(cur, schema, unchecked))
    links |= unchecked - set(orphans)

    units = {str(row["unit_serial_no"]).strip() for row in saved
             if row.get("unit_serial_no") not in (None, "")}
    units |= {str(serial).strip() for _id, serial, link_level, _p, _pl in inside.values()
              if link_level == "unit" and serial}

    # Parents that would be left with nothing inside.
    candidates = defaultdict(set)
    for parent, parent_level in parents:
        if parent and parent_level in CONTAINER_LEVELS:
            candidates[parent_level].add(parent)
    for row in saved:
        for ancestor in above:
            serial = row.get(f"{ancestor}_serial_no")
            if serial not in (None, ""):
                candidates[ancestor].add(str(serial))
    survivors = (sql.SQL("f.{column}::text IS DISTINCT FROM %s").format(
        column=sql.Identifier(column)), (serial_no,))
    emptied, pruned = _prune_empty(cur, schema, table, candidates, links, survivors,
                                   apply=False)

    return {
        "level": level,
        "serial_no": serial_no,
        "links": sorted(links),
        "pruned": pruned,
        "emptied": emptied,
        "units": sorted(units),
        "rows": len(saved),
        "orphans": orphans,
        "children": _children_tree(serial_no, level,
                                   list(inside.values()) + _rows_as_links(level, serial_no, saved)),
    }


def _as_delete_error(exc, level, serial_no):
    """The exception to raise out of a failed delete.

    Everything the delete itself decided already says what went wrong and that
    nothing was deleted. What is left -- a constraint the database refused, a
    column that is not there, no permission to write -- would otherwise reach the
    user as raw driver text with no mention of the container or of the rollback
    that just happened, so it is wrapped. A lost connection is left alone: the
    caller tells the user that separately, and the message here would be a guess
    about a transaction nobody can see the end of.
    """
    if isinstance(exc, (ContainerDeleteError, ValueError)):
        return exc
    if isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)):
        return exc
    if isinstance(exc, psycopg2.Error):
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        return ContainerDeleteError(
            f'The database refused to delete {level} "{serial_no}": {detail} '
            "Nothing was deleted."
        )
    return exc


def _summary(plan):
    return {
        "level": plan["level"],
        "serial_no": plan["serial_no"],
        "children": plan["children"],
        "rows": plan["rows"],
        "edges": len(plan["links"]) + len(plan["pruned"]),
        "units": len(plan["units"]),
        "emptied": plan["emptied"],
        "orphans": len(plan["orphans"]),
    }


def container_delete_preview(level, serial_no, schema="public", table="filling_product_logs"):
    """What deleting one container would remove, without removing anything.

    Returns {"children": [...indented contents...], "rows", "edges", "units",
    "emptied": [parents that would be left empty and removed too], ...}.
    """
    _require_container_level(level, serial_no)
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            return _summary(_plan(cur, schema, table, level, serial_no))


def delete_container(level, serial_no, schema="public", table="filling_product_logs",
                     tag_name=None, expected=None):
    """Delete one container and everything inside it, in a single transaction.

    Removes the container's saved rows, its own link, every link below it, and any
    parent left with nothing inside; releases the serial of every unit that was in
    it, of the container itself, of every container removed beneath it, and of any
    ancestor emptied by this delete (recording `tag_name`) so the roll totals fall
    back and none of those serials still reads as active.

    `expected` is a container_delete_preview() result the user confirmed. If the
    contents no longer match its counts, or the database deletes a different number
    of rows than was planned, nothing is deleted and ContainerDeleteError is raised:
    a half-deleted container is not recoverable the way a half-renamed one is. Any
    other failure is rolled back and reported the same way (see _as_delete_error),
    so the caller never has to show the user raw driver text.
    """
    _require_container_level(level, serial_no)
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            try:
                plan = _plan(cur, schema, table, level, serial_no)
                summary = _summary(plan)
                if expected is not None and any(
                        summary[key] != expected.get(key) for key in ("rows", "edges", "units")):
                    raise ContainerDeleteError(
                        f'The contents of {level} "{serial_no}" changed since you looked '
                        f'(now {summary["rows"]} row(s), {summary["edges"]} link(s), '
                        f'{summary["units"]} unit(s)). Nothing was deleted; open the '
                        "delete again to see what is in it now."
                    )

                container_serials = {plan["serial_no"],
                                     *(child["serial_no"] for child in plan["children"]
                                       if child["level"] != "unit"),
                                     *(item["serial_no"] for item in plan["emptied"])}
                _set_serials_inactive(cur, schema,
                                      [*plan["units"], *container_serials], tag_name)
                links = sorted(plan["links"] + plan["pruned"])
                lost = sorted(set(links) - set(_delete_links(cur, schema, links)))
                if lost:
                    raise ContainerDeleteError(
                        f'The links of {level} "{serial_no}" changed while deleting: '
                        f'{len(lost)} of {len(links)} link(s) '
                        f'({", ".join(str(link) for link in lost[:5])}'
                        f'{", ..." if len(lost) > 5 else ""}) were gone by the time the '
                        "delete ran. Nothing was deleted; someone else may be working on "
                        "the same container. Open the delete again to see what is in it now."
                    )
                cur.execute(
                    sql.SQL("DELETE FROM {flat} WHERE {column}::text = %s").format(
                        flat=_flat_table(schema, table),
                        column=sql.Identifier(f"{level}_serial_no")),
                    (serial_no,),
                )
                if cur.rowcount != plan["rows"]:
                    raise ContainerDeleteError(
                        f'The rows of {level} "{serial_no}" changed while deleting '
                        f'({cur.rowcount} row(s) deleted, {plan["rows"]} planned). '
                        "Nothing was deleted; open the delete again to see what is in "
                        "it now."
                    )
                conn.commit()
            except Exception as exc:
                with contextlib.suppress(Exception):
                    conn.rollback()
                clearer = _as_delete_error(exc, level, serial_no)
                if clearer is exc:
                    raise
                raise clearer from exc
    return {"rows": summary["rows"], "edges": summary["edges"],
            "units": summary["units"], "emptied": summary["emptied"],
            "orphans": summary["orphans"]}
