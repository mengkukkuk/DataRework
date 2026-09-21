"""Public database API for the GUI and the serial-store sync."""

# First: credentials are captured from os.environ when this is imported.
from . import connection
from .connection import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, get_connection
from .hierarchy import (LEVELS, CONTAINER_LEVELS, STAGING_EDGE_TABLE,
                        SERIAL_DATA_TABLE, SharedEdgeError, SerialConflictError,
                        SerialInventoryError, ContainerDeleteError)
from .auth import authenticate
from .schema import get_columns, get_primary_key_columns
from .queries import fetch_distinct_values, query_rows, save_changes, container_groups
from .edge_mirror import update_staging_serial_data, save_grid_changes
from .containers import (container_serials, container_children, rename_children,
                         container_rename_preview, rename_container)
from .deletion import container_delete_preview, delete_container

__all__ = [
    "connection",
    "DB_HOST",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "get_connection",
    "LEVELS",
    "CONTAINER_LEVELS",
    "STAGING_EDGE_TABLE",
    "SERIAL_DATA_TABLE",
    "SharedEdgeError",
    "SerialConflictError",
    "SerialInventoryError",
    "ContainerDeleteError",
    "authenticate",
    "get_columns",
    "get_primary_key_columns",
    "fetch_distinct_values",
    "query_rows",
    "container_groups",
    "save_changes",
    "update_staging_serial_data",
    "save_grid_changes",
    "container_serials",
    "container_children",
    "rename_children",
    "container_rename_preview",
    "rename_container",
    "container_delete_preview",
    "delete_container",
]
