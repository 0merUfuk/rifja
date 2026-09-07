# Security

Report suspected vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/0merUfuk/rifja/security/advisories/new).
Include the affected version, a synthetic reproduction, expected impact and any
workaround. Do not include real credentials or private session transcripts.

The latest published 0.1.x release receives fixes. Historical local release
candidates are superseded. There is no guaranteed response-time SLA.

Rifja reads explicitly registered local inputs and stores its own
state. It does not execute transcript instructions or contact a model service.
Redaction is best effort and is not encryption. Review exported context before
sharing it. Installation may download package-manager dependencies; normal
collection and queries operate offline. See the [threat model](docs/rifja-threat-model.md).
