# Commitment for the blind list 3 package

Everything below was computed when the files were made. The key (which line has which
of our labels) stays private until both labellers have handed in their labels. Its
SHA-256 is published now, so that when the key is published later anyone can check it
was not changed in between: `sha256sum list3-key.tsv` must give the value below.

The key file is UTF-8, no BOM, LF line endings, one header line, then one line per
item sorted by `source_line`; columns `id`, `source_line` (line number in the source
file, whose first line is a header), `label` (red / yellow / green), `group` (the
line kind(s) and source, joined with `+` and `|`).

Note: the source labels were already visible in the public repository before this
package was made (see PROTOCOL.md), so the key does not hide anything that cannot be
looked up. The hash proves the key was fixed before any outside label existed and
that the published IDs map to the lines as stated.

| File | SHA-256 |
|---|---|
| `private/list3-key.tsv` (the key, not published yet) | `389799b9ebedd8a9ca1503a888a44eb900ec38a0464f1d0ead78076402fafd74` |
| `list3-blind-A.tsv` | `fe279339d644c0a204ee6fe417b7515b0548c186e8a7e2332dc7af7a33ab2008` |
| `list3-blind-B.tsv` | `d69708b7b518add25b940bab10519793026d01e4f8a559c9aaa62bfdefaae8dc` |
| `list3-blind-A.csv` | `4ba600af4bd35d5d3c141551e094d402362f20bd25e15af77c3635add720eef9` |
| `list3-blind-B.csv` | `632bff99bdbfd96b20cdb47f0bb1466e8b952aae0e8cdcd398197e6065afc795` |
| source `tools/search_eval/lists/list3.jsonl` as stored in git (LF; `git cat-file blob <commit>:tools/search_eval/lists/list3.jsonl`) | `c6a47f5addbdf7b54e7ac7e2859b7ffdcb7813d66f63922a0e6784724c7512bb` |
| the same file as checked out on Windows with `core.autocrlf=true` (CRLF), the copy the script read | `29774df65c94b7e78ef4ebfd12915d58c35c2f1b77d6e8581bc8585d6396586b` |
| `make_blind.py` (the script that made these files) | `9159f63ae06475dde210615a514b453726e7ecd235cd0bda303286a01e063d09` |

Lines: 531 (199 red, 78 yellow, 254 green).
Python: 3.14.10 (win32).

How the randomness was drawn: the IDs with `secrets.token_hex(4)` (prefix `L3-`), and
each of the two orders with one call of `secrets.SystemRandom().shuffle`, which uses
the operating system's cryptographic random source. Nothing is seeded, so the draws
cannot be repeated; the two published files are the record of them.

Command: `python make_blind.py --source list3.jsonl` (run from a folder holding a copy of the list).

The files in this folder are stored byte for byte (`.gitattributes`: `* -text`), so `sha256sum` on a fresh clone gives the values above on any system. The `.csv` files have CRLF line endings and a BOM for Excel; everything else is LF.
