#!/usr/bin/env node
import('../src/cli.js')
  .catch((err) => {
    console.error('cine-cli failed to start:', err);
    process.exit(1);
  });
