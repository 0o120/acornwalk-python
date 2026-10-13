import * as walk from './acorn-walk-8.15.0.mjs';
import fs from 'node:fs';
const fixtures = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = fixtures.map(root => {
  const full = [], ancestors = [];
  walk.full(root, (node, state, category) => full.push([node.testId, category]));
  walk.fullAncestor(root, (node, state, stack, category) => ancestors.push([node.testId, category, stack.map(n => n.testId)]));
  return {full, ancestors};
});
process.stdout.write(JSON.stringify(result));
