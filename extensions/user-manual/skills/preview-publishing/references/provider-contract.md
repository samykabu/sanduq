# Provider adapter contract

Store an approved descriptor at `User-Manual/providers/<provider-id>/preview.yml` with:

- provider id and approval status;
- official documentation source and review date;
- allowed audiences and whether each is public or authenticated;
- workflow file and pinned action/runtime versions;
- required secret and variable **names**, never their values;
- deployment command or action inputs;
- preview URL output contract;
- teardown/expiry behavior;
- fork-PR behavior and failure fallback.

The provider workflow runs only after audit and audience builds succeed. It consumes generated site
directories, not arbitrary production data. It must emit one URL per deployed edition, preserve the
private artifact link, and update the PR comment through a stable marker.

Reject an adapter when an internal edition lacks enforced authentication, credentials could reach
forked code, deployment has no expiry/cleanup strategy, or the provider cannot prevent secret and
production-data exposure.
