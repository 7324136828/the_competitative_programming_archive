export const MAX_SOURCE_BYTES = 2 * 1024 * 1024;
export const SOURCE_FILE_ACCEPT = '.py,.cpp,.cc,.cxx,.java,.txt';

const fileLanguages = { py: 'python', cpp: 'cpp', cc: 'cpp', cxx: 'cpp', java: 'java' };
const runtimeHelp = { python: 'Python 3', cpp: 'a C++ compiler', java: 'a Java JDK' };

export async function readSourceFile(files, currentLanguage, availableLanguages) {
  if (files.length !== 1) throw new Error('Choose or drop one source file at a time.');
  const file = files[0];
  const extension = file.name.split('.').pop().toLowerCase();
  if (!file.name.includes('.') || ![...Object.keys(fileLanguages), 'txt'].includes(extension)) {
    throw new Error('Use a .py, .cpp, .cc, .cxx, .java, or .txt source file.');
  }
  if (file.size > MAX_SOURCE_BYTES) throw new Error('Source files must be 2 MiB or smaller.');
  const language = extension === 'txt' ? currentLanguage : fileLanguages[extension];
  const available = availableLanguages.find(item => item.id === language);
  if (!available) {
    throw new Error(`This file needs ${runtimeHelp[language] || 'a supported runtime'} on the server. Install it and reload the page, then upload again.`);
  }

  let bytes;
  try {
    bytes = await file.arrayBuffer();
  } catch {
    throw new Error('The source file could not be read. Choose the file again.');
  }
  if (bytes.byteLength > MAX_SOURCE_BYTES) throw new Error('Source files must be 2 MiB or smaller.');
  let code;
  try {
    code = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    throw new Error('Save the source file as UTF-8 text, then upload again.');
  }
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(code)) {
    throw new Error('This appears to be a binary file. Choose a UTF-8 source code file.');
  }
  return { code, language, name: file.name, label: available.label };
}
