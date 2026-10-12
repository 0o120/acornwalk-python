import * as walk from './acorn-walk-8.15.0.mjs';
import fs from 'node:fs';
const roots = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = roots.map(root => {
  const queries = [];
  for (let pos = 0; pos <= root.end + 1; pos++) {
    for (const test of [null, 'Identifier', 'Expression']) {
      const matched = (value) => value ? value.node.testId : null;
      queries.push([
        matched(walk.findNodeAround(root, pos, test)),
        matched(walk.findNodeAfter(root, pos, test)),
        matched(walk.findNodeBefore(root, pos, test)),
        matched(walk.findNodeAt(root, pos, null, test)),
        matched(walk.findNodeAt(root, null, pos, test))
      ]);
    }
  }
  return queries;
});
process.stdout.write(JSON.stringify(result));
