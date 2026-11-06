# Feature: Period scheduling

## Requirements

- **FR-001**: The system rejects a period that overlaps an existing period and names the affected days.
- **FR-002**: Capacity accepts whole numbers 1 to 8 and rejects any other value.
- **FR-003**: Signing out revokes the device session on the server and clears the stored credential from
  the operating-system keyring.
- **FR-004**: Mobile access is out of scope for this feature; it ships on the web client only.
