# Hypercorn oracle-contamination pilot (excluded)

This interrupted pilot is excluded from all headline results. Its `fresh_import`
reference imported the final source from the measured project directory. For a
same-size edit whose mtime was deliberately restored, CPython could accept the
pre-edit `__pycache__` entry, causing both the running server and the purported
reference to return the old value. The pilot therefore exposed an oracle defect
rather than establishing correctness. The corrected protocol executes the
final source bytes in an isolated fresh interpreter with bytecode writing
disabled. The original partial records are retained to make the correction
auditable.
