# --- packaging hierarchy -----------------------------------------------------
#
# filling_product_logs is a flattened chain: one row per unit, carrying the
# serial/roll of every container it sits in. staging_product_logs is the edge
# table behind it -- one row per child->parent link:
#
#     serial_no [serial_label_code]  ->  parent_serial_no [parent_serial_label_code]
#     source_roll_no                 ->  target_roll_no
#
# A row's <level>_source_id is the edge where that level is the CHILD; the same
# edge id also appears as <parent>_target_id (verified: the two columns never
# disagree). So renaming e.g. a display serial has to touch two edges -- the
# display->carton edge where display is the child, and the unit->display edge
# where it is the parent.
LEVELS = ["unit", "display", "inner", "carton"]

# Levels whose serial names a *container* rather than the row itself. One
# display is shared by ~6 filling_product_logs rows and one carton by ~130, so
# these can never be edited as a per-row cell -- renaming them is a
# whole-container operation (see rename_container).
CONTAINER_LEVELS = ("display", "inner", "carton")

STAGING_EDGE_TABLE = "staging_product_logs"
SERIAL_DATA_TABLE = "staging_serial_data"


class SharedEdgeError(Exception):
    """A serial/roll edit would rewrite container rows the user never saw.

    display/carton edges are shared by roughly six sibling units each, so
    editing one row's display_serial_no would silently rename it for all of
    them. Renaming a shared container is a deliberate act, not a side effect of
    a cell edit, so the save is refused and the user is told the blast radius.
    """


class SerialConflictError(Exception):
    """A rename collided with uq_staging_product_logs_business_key."""


class SerialInventoryError(Exception):
    """A serial being activated is absent from (or duplicated in) the pool.

    staging_serial_data is what serial_store_aio counts to derive used_serials,
    so activating a serial with no inventory row leaves that total short
    forever -- silently, because the rename itself would still report success.
    The write is refused instead, rolling the whole transaction back.
    """
