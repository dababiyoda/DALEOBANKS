import { useEffect, useRef } from 'react';
import * as monaco from 'monaco-editor';

interface MonacoEditorProps {
  value: string;
  onChange: (value: string) => void;
  language?: string;
  height?: string;
  options?: monaco.editor.IStandaloneEditorConstructionOptions;
}

export default function MonacoEditor({
  value,
  onChange,
  language = 'javascript',
  height = '400px',
  options = {}
}: MonacoEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const monacoRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);

  useEffect(() => {
    if (editorRef.current) {
      // Configure Monaco themes for dark/light mode
      monaco.editor.defineTheme('custom-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [],
        colors: {
          'editor.background': '#0f172a', // slate-900
          'editor.foreground': '#f8fafc', // slate-50
        }
      });

      monaco.editor.defineTheme('custom-light', {
        base: 'vs',
        inherit: true,
        rules: [],
        colors: {
          'editor.background': '#ffffff',
          'editor.foreground': '#0f172a',
        }
      });

      // Detect dark mode
      const isDark = document.documentElement.classList.contains('dark');
      
      monacoRef.current = monaco.editor.create(editorRef.current, {
        value,
        language,
        theme: isDark ? 'custom-dark' : 'custom-light',
        automaticLayout: true,
        scrollBeyondLastLine: false,
        minimap: { enabled: false },
        fontSize: 14,
        lineHeight: 1.6,
        fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
        ...options,
      });

      monacoRef.current.onDidChangeModelContent(() => {
        const currentValue = monacoRef.current?.getValue() || '';
        onChange(currentValue);
      });

      // Listen for theme changes
      const observer = new MutationObserver(() => {
        const isDark = document.documentElement.classList.contains('dark');
        monaco.editor.setTheme(isDark ? 'custom-dark' : 'custom-light');
      });

      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['class']
      });

      return () => {
        observer.disconnect();
        monacoRef.current?.dispose();
      };
    }
  }, []);

  useEffect(() => {
    if (monacoRef.current && value !== monacoRef.current.getValue()) {
      monacoRef.current.setValue(value);
    }
  }, [value]);

  return (
    <div 
      ref={editorRef} 
      style={{ height }}
      className="border border-border rounded-lg overflow-hidden"
    />
  );
}
