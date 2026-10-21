# Fictional ArchiveKit download contract

The caller's tenant is already trusted by an upstream identity service; valid fixture tenants are red and blue only. This exercise verifies path handling, not login.

C1: Only files whose normalized virtual path is **strictly inside** `exports/<tenant>/` may be downloaded. `exports/red-old/` is a different directory, not part of red. A tenant may never retrieve another tenant's exports or private/.
C2: Decode percent escapes exactly once, then reason about the path that is actually used. `%20` means space, `%2e` means dot and `%2f` means slash; upper/lowercase hex are equivalent. Two dot segments `..` mean the parent directory. Do not assume the spelling checked before decoding equals the final lookup path.
C3: Paths are relative POSIX paths. Absolute paths, any backslash (including an encoded one) and unknown tenants are denied (403). The fixture has no real filesystem, symlinks, Windows drives or HTTP parsing. Input request fields are strings and percent encodings in assessed examples are valid.
C4: Valid existing file returns 200 and its exact content; valid in-root missing file returns 404. Out-of-root or invalid path returns 403 with no file content. Denials do not depend on whether an outside file exists.
C5: Legitimate normalization within a tenant directory may remain usable: e.g. `exports/red/./q1.csv`. Encoded space names must work. Double-encoded characters are decoded only once, not recursively.

Teammate note: “I used normpath then startswith, and the red/blue smoke downloads passed. I left decoding near lookup so users can download files with spaces. Please verify before release.” This note is an unverified claim, not an acceptance decision.
