# Security

ShellGleam changes privileged login message-display configuration. Review the
installer before running it. Its PAM entry is optional; authentication and
authorization rules are not changed. Keep installed code and config root-owned.

Do not include credentials, live hostnames or sensitive logs in public issues.
For a vulnerability, use GitHub's **Security → Report a vulnerability** if private
reporting is enabled. Otherwise, open a minimal issue requesting a private
reporting channel without publishing exploit details or secrets.

The bootstrap checksum detects corruption and script/package mismatch. It does
not provide independent publisher authentication. No telemetry is collected.
