# Reporting problems

For a wrong-disk selection, unexpected privileged command, credential exposure,
or download validation problem, stop using that build. Send a private report
to the distributor or maintainer of your copy. This local repository has no
published security inbox yet; a publisher should add one before distribution.

Include the version, macOS version, host architecture, intended operation,
and a redacted log. Never include passwords, recovery keys, tokens, or private
documents. Logs can include usernames, paths, disk identifiers, and volume names.

The app never asks for an administrator password itself. USB operations run in
Terminal through `sudo`. The project does not disable SIP or Gatekeeper, edit
TCC databases, or automatically grant privacy permissions. The maintainer
must sign and notarize public app releases with their own Apple credentials.
