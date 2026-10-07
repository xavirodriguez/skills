# XMAP evidence model

An XMAP can expose linker-level information that is otherwise missing from a ROM-only analysis:

- original symbol names;
- linked addresses;
- section placement;
- section boundaries;
- explicit symbol sizes;
- neighbouring symbols;
- linker-generated symbols.

Treat these as structural evidence. Validate any ROM offset mapping against the executable header, load addresses and binary contents.

The generic parser intentionally preserves unclassified lines so that a real sample can drive a format-specific parser later.
