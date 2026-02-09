## Security

Please see [SECURITY](./SECURITY) for vulnerability reporting guidelines.

## Documentation Safety

Examples in skills and references must follow secure defaults:

- Use least-privilege permissions — don't suggest `ALL PRIVILEGES` when a narrower grant suffices
- If an example requires elevated permissions, state it explicitly (e.g. "requires workspace admin")
- Prefer scoped tokens over broad credentials
- Obfuscate sensitive values: use placeholder workspace IDs (`1111111111111111`), URLs (`company-workspace.cloud.databricks.com`), and never include real tokens or passwords

## Developer Certificate of Origin

To contribute to this repository, you must sign off your commits to certify 
that you have the right to contribute the code and that it complies with the 
open source license. The rules are pretty simple, if you can certify the 
content of [DCO](./DCO), then simply add a "Signed-off-by" line to your 
commit message to certify your compliance. Please use your real name as 
pseudonymous/anonymous contributions are not accepted.

```
Signed-off-by: Joe Smith <joe.smith@email.com>
```

If you set your `user.name` and `user.email` git configs, you can sign your 
commit automatically with `git commit -s`:

```
git commit -s -m "Your commit message"
```