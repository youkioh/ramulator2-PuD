# MIMDRAM Geometry

## Source

MIMDRAM evaluation configuration and data-mapping description provided for
this project.

## Source-backed MIMDRAM configuration

- DDR4-2400
- 1 channel
- 8 chips
- 4 ranks
- 16 banks per rank
- 8 KiB row size
- 16 mats per chip
- 1K rows per mat
- 512 columns per mat
- Up to 128 mats in a DDR4 module
- A 7-bit logical mat ID:
  - 3 most-significant bits identify the chip.
  - 4 least-significant bits identify the mat.
- In the example 8-chip, 16-mat-per-chip organization, a 64 B cache line is
  distributed across all 128 mats.
- Mat interleaving depends on the DRAM chip organization.

## Project modeling assumptions

- DDR4_PuD currently models `rows_per_subarray = 1024`.
- For `DDR4_8Gb_x8`, this gives 64 logical subarrays per bank.
- `subarray_id = row / 1024`.
- `local_row = row % 1024`.
- Contiguous groups of 1024 device-visible row IDs are treated as one logical
  subarray.
- This grouping is a simulator assumption, not a verified physical DDR4
  address mapping.
- Mat-level mapping is not yet defined.
