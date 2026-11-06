# Discovery and module approval

Detect modules from solution/workspace boundaries, domain folders, route groups, navigation menus,
mobile app areas, API tags, bounded contexts, database contexts, deployment units, specifications,
and existing manuals. Record evidence paths for every proposed module.

Prefer user-recognizable product modules over technical projects. A service is not automatically a
manual module; several services may implement one user-facing capability. Conversely, a large
frontend may contain several modules.

Present the map for approval during initialization. Store approved entries in `manual.yml` with:
`id`, `name`, `description`, `status`, `interfaces`, `audiences`, and `evidence`. Later features may
add `proposed` entries, but stable navigation contains approved modules only.
