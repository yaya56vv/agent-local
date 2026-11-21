---
name: check-disk-space
description: "Measure the free space on a disk and identify the heaviest files in a folder using the PowerShell terminal, when the user asks how much space is left or what takes up the most space."
---

## When to Use It
When the user asks for the free space on a disk, the heaviest files in a folder, or whether there is enough space for an installation or download.

## Steps
1. Measure free space: Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'", then display FreeSpace and Size converted to GB.
2. List the heaviest files in the requested folder: Get-ChildItem -Path <folder> -File -Recurse -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First 5, with size in MB or GB.
3. Present results in clear sentences (rounded sizes, readable names).
4. If the user wants to free up space, suggest what could be removed and wait for approval: we never delete without consent, and it's better to move than delete.

## Pitfalls to Avoid
- Get-Volume may fail (« the Storage module could not be loaded »): use Get-CimInstance Win32_LogicalDisk instead.
- Never provide raw sizes in bytes: convert to MB or GB.
- Never delete or move files without user consent; read-only is safe.
- The Local Agent installation folder is forbidden, even for a simple listing.