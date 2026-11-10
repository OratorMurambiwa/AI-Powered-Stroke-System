import { connectDB, disconnectDB } from '../config/database';
import { bootstrapAdmin, consumeDelivery } from '../services/identity.service';
import { createInterface } from 'node:readline/promises';
// Human operator stdin, never passwords/tokens in command arguments or application logs.
async function main(): Promise<void> {
  const input = createInterface({ input: process.stdin, output: process.stderr });
  try {
    await connectDB();
    const operator = await input.question('Operator reference: ');
    if (process.argv[2] === 'bootstrap') {
      const email = await input.question('New administrator email: ');
      const name = await input.question('New administrator name: ');
      const reason = await input.question('Authorization/change reference: ');
      process.stdout.write(JSON.stringify(await bootstrapAdmin({ email, name, reason }, operator)) + '\n');
    } else if (process.argv[2] === 'deliver') {
      const id = await input.question('Encrypted delivery ID: ');
      const confirmed = await input.question('Registered recipient/channel verified and secure handoff ready? Type HANDOFF: ');
      if (confirmed !== 'HANDOFF') throw new Error();
      // Sensitive one-time output: use only a private operator terminal, never redirect to logs.
      process.stdout.write(JSON.stringify(await consumeDelivery(id, operator)) + '\n');
    } else throw new Error();
  } finally { input.close(); await disconnectDB(); }
}
void main().catch(() => { process.stderr.write('Identity operator action failed; no credentials logged.\n'); process.exitCode = 1; });
