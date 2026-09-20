import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MAX_SOURCE_BYTES, readSourceFile } from './sourceFiles.js';

const languages = [{ id: 'python', label: 'Python 3' }, { id: 'cpp', label: 'C++' }];
const file = (name, code) => new File([code], name, { type: 'text/plain' });

test('source files select their language while plain text keeps the editor language', async () => {
  for (const extension of ['cpp', 'cc', 'CXX']) {
    const result = await readSourceFile([file(`solution.${extension}`, '// hello\r\n')], 'python', languages);
    assert.equal(result.language, 'cpp');
    assert.equal(result.code, '// hello\r\n');
  }
  assert.equal((await readSourceFile([file('code.py', '# café\nprint("你好")')], 'cpp', languages)).language, 'python');
  assert.equal((await readSourceFile([file('code.txt', '')], 'cpp', languages)).code, '');
  assert.equal((await readSourceFile([file('code.txt', '')], 'cpp', languages)).language, 'cpp');
  assert.equal((await readSourceFile([file('bom.py', '\ufeffprint(1)')], 'python', languages)).code, 'print(1)');
});

test('invalid files fail before replacing any editor content', async () => {
  await assert.rejects(readSourceFile([], 'python', languages), /one source file/);
  await assert.rejects(readSourceFile([file('a.py', ''), file('b.py', '')], 'python', languages), /one source file/);
  await assert.rejects(readSourceFile([file('a.exe', '')], 'python', languages), /source file/);
  await assert.rejects(readSourceFile([file('Main.java', '')], 'python', languages), /Java JDK/);
  await assert.rejects(readSourceFile([file('binary.py', 'x\0y')], 'python', languages), /binary file/);
  await assert.rejects(readSourceFile([file('invalid.py', new Uint8Array([0xff, 0xfe]))], 'python', languages), /UTF-8/);
  await assert.rejects(readSourceFile([{ name: 'large.py', size: MAX_SOURCE_BYTES + 1, arrayBuffer: () => assert.fail('oversized file must not be read') }], 'python', languages), /2 MiB/);
  await assert.rejects(readSourceFile([{ name: 'lost.py', size: 1, arrayBuffer: () => Promise.reject(Error('unreadable')) }], 'python', languages), /could not be read/);
});
