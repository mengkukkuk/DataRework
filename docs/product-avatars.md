# Product avatars

Cards use the saved database `product_name` (or `FILTER_COLUMN_PRODUCT_NAME`),
not the text currently typed in the product filter. Matching normalizes Unicode,
case, whitespace and underscores; it does not use partial/fuzzy matching.

- Unit: put `<product_name>.png` in `images/` or `images/unit/`.
- Other levels: use `images/display/`, `images/inner/`, or `images/carton/`.
- For a different filename or database alias, add an exact product-name entry
  under the appropriate level in `images/avatars.json`. Paths are relative to
  `images/`. For example: `"Exact database name": "carton/product-box.png"`.

PNG, JPEG and WebP are supported. Restart the app after adding images or mappings.
The build bundles the entire images folder. Thumbnails are cached and preserve
aspect ratio; missing, unreadable, unmatched, or mixed-product images fall back
to the normal text card. A parent box uses only an image configured for its own
level, and only when its records contain one normalized product name.
