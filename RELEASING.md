# Releasing

This repo is released via tagged GitHub releases. Releases are cut from `main`.

## How to cut a release

Run the `Release` workflow from the [Actions tab](https://github.com/databricks/databricks-agent-skills/actions/workflows/release.yml) and supply the version (e.g. `v0.3.0`).

The workflow:

1. Validates the version matches `vX.Y.Z`.
2. Creates an **annotated** git tag (`git tag -a`).
3. Pushes the tag to origin.
4. Creates a GitHub Release with auto-generated notes (`--verify-tag` confirms the tag exists).

## Verifying a release tag

```bash
git fetch --tags
git tag -v v0.3.0
```

`git tag -v` only works on annotated tags — lightweight tags have no metadata to verify.

## Signing — status

The annotated-tag step above is a prerequisite for signing; without it, there is nothing to sign. Signing itself is **not yet enabled**: today the workflow creates annotated tags without a GPG/Sigstore signature.

Path forward:

- **GPG**: provision a release-identity GPG key, store the private key + passphrase in GH Actions secrets, and add a sign step that runs `git tag -s` instead of `git tag -a`. Verification stays `git tag -v`.
- **Sigstore (gitsign)**: install [`sigstore/gitsign`](https://github.com/sigstore/gitsign) in the workflow and set `gpg.format=x509`. No long-lived secret; the runner's OIDC token is the identity. Verification stays `git tag -v` plus `gitsign verify`.

Either approach satisfies the `README.md` "Integrity" claim that future tags are signed and verifiable. The README claim was added when the repo was still using lightweight tags — switching to annotated tags here unblocks it.

## Existing tags

`v0.1.0` through `v0.2.1` are **lightweight** tags (`git for-each-ref --format='%(objecttype)' refs/tags` returns `commit`, not `tag`). They cannot be retroactively GPG-signed without re-tagging. If the project wants verifiable history, two options:

- Delete and re-create as annotated signed tags (rewrites the public tag history — coordinate with downstream consumers).
- Leave them as-is and start signing from the next release.
