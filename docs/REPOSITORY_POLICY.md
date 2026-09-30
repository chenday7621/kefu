# Repository policy

Internal repository: full experimental provenance, legacy datasets, private review
materials, frozen raw results and credentials kept out of public version control.

Public repository: sanitized project-code snapshot, dependency integration and
aggregate evidence. It has its own initial Git history; it is not a clone or history
rewrite of the internal repository. The two repositories do not replace each other.

No internal remote or credentials are inherited. A GitHub target must be explicitly
provided and reviewed before adding a remote or pushing.

Only the explicit allowlist is published. Data, external assets and raw trajectories
with uncertain distribution rights remain excluded. Running the official benchmark
requires obtaining its fixed version separately and respecting its applicable terms.
No blanket reuse license for owner-written project code has been chosen on the owner's
behalf. Public visibility is not a grant of an MIT/Apache license. The upstream MIT
notice for attributed instruction text is preserved in THIRD_PARTY_NOTICES.md.
