import { expect, test } from './native-harness';

test('sign-out calls the revoke endpoint', async ({ app, server }) => {
  await app.signOut();
  expect(server.revokedSessions()).toHaveLength(1);
});
