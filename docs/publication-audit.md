# Public content and history audit

## Scope and method

The baseline audit inspected all 148 tracked files at the final local-only candidate
and all 55 files at its parent, including source, tests, fixture JSON, SVG screenshots,
sample reports, qualification records, documentation, workflow and license. Those
two baseline commits' author/committer metadata and messages were checked separately.

Procedures: `git ls-files`; `git rev-list --all`; `git ls-tree -r --name-only` and
`git show` for every reachable revision; `git grep` and current-tree `rg` scans for
personal paths/identities, private hostnames, email addresses, IP literals, private-key
headers, token patterns and proprietary organization/project references. IP literals
were enumerated and reviewed, not assumed safe because an address is private.
Fixtures, screenshots and sample reports were examined for real-infrastructure data.

## Baseline findings

The baseline contained two publication blockers:

- One commit's author/committer metadata used personal identity and a personal email
  rather than the generic project identity.
- The actual-host qualification JSON retained a named private mount path and four
  complete container overlay identifiers in command arguments. Keeping output byte
  counts did not sanitize command arguments.

The initial commit used generic DCT contributor identity. Both commits' messages
contained no private information. The baseline IP set was only `0.0.0.0` and the
RFC 5737 `192.0.2.0/24` documentation range. Fixture hostnames, users, UUIDs, GPU
identifiers, MACs and cgroups are synthetic, generic examples. Public NVIDIA utility
names and telemetry examples are ordinary interoperability content, not proprietary
company material. No credential, SSH private key, API key, private home path or
proprietary implementation content was identified in tracked baseline files.

## Release disposition

Both unpublished commits were rewritten using generic project contributor metadata.
Historical qualification command arguments were replaced by command name and argument
count; the final qualification script follows the same policy. An independent scan
of both reachable commits and the integrated candidate found no remaining publication
blocker. Real inventories, SSH configuration and the recovery bundle remain outside
the tracked repository. Only main is a publication ref; no backup branch/tag exists.

Final verification also audits built wheel/sdist contents and regenerated synthetic
screenshots/reports. Reflogs and unreachable pre-rewrite objects are removed after
final review, with recoverability preserved solely outside the repository. No public
artifact identifies the private remote qualification host. Synthetic negative tests
mention generic private-key/home-path examples intentionally to test exclusions.

The audit uses targeted pattern searches and manual inspection; it is not a proof
that arbitrary secrets or undisclosed proprietary material cannot exist. Public
release authorization remains a separate founder decision. No publication occurred.

## Release packaging audit

The packaging lane independently audited the publishable working tree and all
three then-reachable commits, including generic project commit identities.
Installer/uninstaller scripts, ownership manifests, tests, installation instructions,
qualification records and preliminary wheel/source/Linux archives contained no
private identifiers, credentials or proprietary infrastructure material.
The only IPv4 literals remain `0.0.0.0` and documentation range `192.0.2.0/24`;
synthetic netrc input in installer tests is explicitly artificial.

Final regenerated release assets and all four reachable commits are rechecked at
closeout; identifying-pattern and archive-content checks pass. Only main remains
a publication ref, with no Git remote or unreachable historical objects. Archives exclude environments, Git metadata and local reports;
Linux bundle owner headers are zero/empty. Installer dependency downloads use
staged HOME, no pip cache, null netrc, disabled keyring and no proxy environment.
No credential files or installation logs are distributed. The audit limits above
still apply; no publication or remote creation occurred.
