# Contributing

Small, focused pull requests are welcome. Explain the behavior being changed,
include meaningful regression tests, and keep login fast and failure-tolerant.

Use Python 3.9+ and the standard library. Run:

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/bootstrap.sh deploy.sh
sh -n setup.sh
python3 scripts/build_site.py
```

Website source lives in `site/`; generated output belongs in `_site/` and is
not committed. Please use fictional hostnames and addresses from documentation
ranges in examples. Never submit credentials, live server output, private
addresses or customer deployment notes. Review both source and built artifacts.

Installer tests operate in temporary filesystem roots. Test real SSH/PAM changes
only on a disposable VM with a second recovery session. Preserve rollback,
symlink metadata and concurrent-session behavior when changing installation.
