# Cheap reads

Read what you need, not what is there.

- Before reading a file, search it: `grep -n "<pattern>" <file>` or `rg -n`. Read a range around the
  hit, not the whole file.
- Read line ranges when a file is long: `sed -n '120,180p' <file>`, or the read tool's `offset` and
  `limit`. Read the top of a file only to know what it is.
- Never read a whole large file to find one thing in it. Two greps are cheaper than one 3,000-line
  read, and a 3,000-line read cannot be undone: it stays in the context for every later step.
- `ls`, `wc -l`, `git diff --stat` first. A count tells you whether a read is worth it.
- If a read returns far more than you needed, say what you were looking for and move on instead of
  re-reading around it.
