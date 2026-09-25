import React, { useState } from 'react';
import { 
  X, 
  Upload, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw
} from 'lucide-react';
import { useProject } from '../../context/ProjectContext';
import { api } from '../../api/client';

interface ImportStoriesModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ImportStoriesModal: React.FC<ImportStoriesModalProps> = ({ isOpen, onClose }) => {
  const { currentProject, projects, triggerRefresh } = useProject();
  const [projectId, setProjectId] = useState<string>(currentProject?.id || projects[0]?.id || '');
  const [epicName, setEpicName] = useState('Competitive Programming Mastery');
  const [featureName, setFeatureName] = useState('Core Algorithms');
  const [jsonText, setJsonText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successResult, setSuccessResult] = useState<any | null>(null);

  if (!isOpen) return null;

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setFileName(file.name);
    setJsonText('');
    setErrorMsg(null);
    setUploadProgress(null);
    setIsProcessing(false);
  };

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile && !jsonText.trim()) {
      setErrorMsg('Please upload a JSON file or paste valid JSON data.');
      return;
    }

    setIsSubmitting(true);
    setUploadProgress(selectedFile ? 0 : null);
    setIsProcessing(false);
    setErrorMsg(null);
    setSuccessResult(null);

    try {
      let res: any;
      if (selectedFile) {
        res = await api.importStoriesFile(selectedFile, {
          projectId,
          epicName: epicName.trim() || undefined,
          featureName: featureName.trim() || undefined,
          onProgress: setUploadProgress,
          onProcessing: () => {
            setUploadProgress(100);
            setIsProcessing(true);
          },
        });
      } else {
        let parsedData: any;
        try {
          parsedData = JSON.parse(jsonText.trim());
        } catch (err: any) {
          throw new Error(`JSON Parse Error: ${err.message}`);
        }
        const payload = Array.isArray(parsedData) ? {
          projectId,
          epicName: epicName.trim() || undefined,
          featureName: featureName.trim() || undefined,
          stories: parsedData,
        } : {
          projectId: parsedData.projectId || projectId,
          epicName: parsedData.epicName || epicName.trim() || undefined,
          featureName: parsedData.featureName || featureName.trim() || undefined,
          stories: parsedData.stories || parsedData.problems || [parsedData],
        };
        res = await api.importStories(payload);
      }
      setSuccessResult(res);
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message || 'Import failed. Check JSON format.');
    } finally {
      setIsSubmitting(false);
      setIsProcessing(false);
    }
  };

  const handleReset = () => {
    setJsonText('');
    setSelectedFile(null);
    setFileName(null);
    setUploadProgress(null);
    setIsProcessing(false);
    setErrorMsg(null);
    setSuccessResult(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-100">
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-100 text-gray-800">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="p-2 bg-blue-100 text-blue-700 rounded-lg">
              <Upload className="w-5 h-5" />
            </span>
            <div>
              <h2 className="font-bold text-base text-[#172B4D]">Import Stories & Problem Sets</h2>
              <p className="text-xs text-gray-500">Maps problem sets to Features and sets of problem sets to Epics</p>
            </div>
          </div>
          <button disabled={isSubmitting} onClick={onClose} className="text-gray-400 hover:text-gray-600 disabled:opacity-40 p-1 rounded-md">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 text-xs">
          {errorMsg && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md flex items-center space-x-2 text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
              <span>{errorMsg}</span>
            </div>
          )}

          {successResult ? (
            <div className="p-6 bg-emerald-50 border border-emerald-200 rounded-xl space-y-3 text-center">
              <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto" />
              <h3 className="text-base font-bold text-emerald-900">Import Successful!</h3>
              <p className="text-xs text-emerald-800">
                Created <strong>{successResult.stories_created ?? successResult.imported ?? 0}</strong> Stories,{' '}
                <strong>{successResult.features_created ?? successResult.features ?? 0}</strong> Features, and{' '}
                <strong>{successResult.epics_created ?? 0}</strong> Epics.
              </p>
              <div className="pt-2 flex justify-center space-x-3">
                <button
                  onClick={handleReset}
                  className="px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-lg font-semibold"
                >
                  Import More
                </button>
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold"
                >
                  View in Board
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleImport} className="space-y-4">
              {/* Target Project */}
              <div>
                <label className="block font-semibold text-gray-700 mb-1">Target Project *</label>
                <select
                  value={projectId}
                  onChange={e => setProjectId(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                >
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.key})</option>
                  ))}
                </select>
              </div>

              {/* Hierarchy Configuration */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-semibold text-gray-700 mb-1">
                    Epic (Set of Problem Sets)
                  </label>
                  <input
                    type="text"
                    value={epicName}
                    onChange={e => setEpicName(e.target.value)}
                    placeholder="e.g. LeetCode 75, Advanced Graph Curriculum"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                  <span className="text-[10px] text-gray-500">Groups related problem set features together</span>
                </div>

                <div>
                  <label className="block font-semibold text-gray-700 mb-1">
                    Feature (Problem Set)
                  </label>
                  <input
                    type="text"
                    value={featureName}
                    onChange={e => setFeatureName(e.target.value)}
                    placeholder="e.g. Dynamic Programming, Two Pointers"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                  <span className="text-[10px] text-gray-500">Default feature category for these stories</span>
                </div>
              </div>

              {/* Upload Dropzone */}
              <div>
                <label className="block font-semibold text-gray-700 mb-1">JSON File Upload</label>
                <div className="border-2 border-dashed border-gray-300 hover:border-blue-500 rounded-xl p-6 text-center cursor-pointer bg-gray-50 transition relative">
                  <input
                    type="file"
                    accept=".json"
                    onChange={handleFileUpload}
                    className="absolute inset-0 opacity-0 cursor-pointer"
                  />
                  <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                  <p className="font-semibold text-gray-700">
                    {fileName ? fileName : 'Click or drag a JSON file here'}
                  </p>
                  <p className="text-[11px] text-gray-500 mt-1">
                    {selectedFile
                      ? `${(selectedFile.size / (1024 * 1024)).toFixed(1)} MiB · uploads directly without loading into the editor`
                      : 'Accepts standard problem archive JSON or Jira story arrays'}
                  </p>
                </div>
              </div>

              {isSubmitting && selectedFile && (
                <div className="space-y-1" aria-live="polite">
                  <div className="flex justify-between text-[11px] text-gray-600">
                    <span>{isProcessing ? 'Processing stories on the server…' : 'Uploading dataset…'}</span>
                    <span>{uploadProgress ?? 0}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-gray-200">
                    <div
                      className={`h-full bg-blue-600 transition-all ${isProcessing ? 'animate-pulse' : ''}`}
                      style={{ width: `${uploadProgress ?? 0}%` }}
                    />
                  </div>
                  {isProcessing && (
                    <p className="text-[10px] text-gray-500">Large imports can take several minutes. Keep this dialog open until it finishes.</p>
                  )}
                </div>
              )}

              {/* Or Paste JSON */}
              <div>
                <label className="block font-semibold text-gray-700 mb-1">Or Paste JSON Data</label>
                <textarea
                  rows={6}
                  value={jsonText}
                  onChange={e => {
                    setJsonText(e.target.value);
                    if (selectedFile) {
                      setSelectedFile(null);
                      setFileName(null);
                      setUploadProgress(null);
                    }
                  }}
                  placeholder={`[\n  {\n    "title": "Two Sum",\n    "problem_statements": "Given an array of integers...",\n    "difficulty": "Easy",\n    "story_type": "coding"\n  }\n]`}
                  className="w-full p-3 font-mono text-[11px] border border-gray-300 rounded-md text-gray-800 focus:ring-2 focus:ring-blue-500 outline-none resize-y"
                />
              </div>

              {/* Actions */}
              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-gray-200">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={isSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-gray-600 hover:text-gray-800 disabled:opacity-40"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || (!selectedFile && !jsonText.trim())}
                  className="px-5 py-2 bg-[#0052CC] hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center space-x-2 transition shadow-xs"
                >
                  {isSubmitting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{isSubmitting ? (isProcessing ? 'Processing Stories…' : 'Uploading…') : 'Import Stories'}</span>
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
