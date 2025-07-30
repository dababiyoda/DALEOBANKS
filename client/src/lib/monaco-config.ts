// Configure Monaco Editor Web Workers to avoid console warnings
// @ts-ignore
self.MonacoEnvironment = {
  getWorkerUrl: function (_moduleId: string, label: string) {
    if (label === 'json') {
      return '/monaco-editor/esm/vs/language/json/json.worker.js';
    }
    if (label === 'css' || label === 'scss' || label === 'less') {
      return '/monaco-editor/esm/vs/language/css/css.worker.js';
    }
    if (label === 'html' || label === 'handlebars' || label === 'razor') {
      return '/monaco-editor/esm/vs/language/html/html.worker.js';
    }
    if (label === 'typescript' || label === 'javascript') {
      return '/monaco-editor/esm/vs/language/typescript/ts.worker.js';
    }
    return '/monaco-editor/esm/vs/editor/editor.worker.js';
  }
};