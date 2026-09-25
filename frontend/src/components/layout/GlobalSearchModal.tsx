import React, { useState, useEffect } from 'react';
import { Search, X, ArrowRight } from 'lucide-react';
import { api } from '../../api/client.js';
import { Issue } from '../../types/index.js';
import { TypeIcon, StatusBadge } from '../common/Badge.js';
import { useProject } from '../../context/ProjectContext.js';

interface GlobalSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const GlobalSearchModal: React.FC<GlobalSearchModalProps> = ({ isOpen, onClose }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [results, setResults] = useState<Issue[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { openIssueDetail } = useProject();

  useEffect(() => {
    if (!isOpen) {
      setSearchTerm('');
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      if (searchTerm.trim().length > 0) {
        setIsLoading(true);
        try {
          const data = await api.getIssues({ query: searchTerm });
          setResults(data);
        } catch (e) {
          console.error(e);
        } finally {
          setIsLoading(false);
        }
      } else {
        // Load recent issues by default
        setIsLoading(true);
        try {
          const data = await api.getIssues({});
          setResults(data.slice(0, 10));
        } catch (e) {
        } finally {
          setIsLoading(false);
        }
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [searchTerm, isOpen]);

  // Handle keyboard shortcut Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/40 backdrop-blur-xs animate-in fade-in duration-100">
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-2xl overflow-hidden animate-in zoom-in-95 duration-100">
        {/* Search Input Bar */}
        <div className="flex items-center px-4 py-3 border-b border-gray-200 space-x-3">
          <Search className="w-5 h-5 text-gray-400" />
          <input
            autoFocus
            type="text"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Search issues by summary, description, or key (e.g. CP-1)..."
            className="flex-1 text-sm bg-transparent outline-none text-[#172B4D] placeholder-gray-400"
          />
          {searchTerm && (
            <button onClick={() => setSearchTerm('')} className="p-1 hover:bg-gray-100 rounded text-gray-400">
              <X className="w-4 h-4" />
            </button>
          )}
          <kbd className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded text-gray-400 font-mono">ESC</kbd>
        </div>

        {/* Results List */}
        <div className="max-h-96 overflow-y-auto p-2">
          {isLoading ? (
            <div className="py-8 text-center text-xs text-gray-400">Searching work items...</div>
          ) : results.length === 0 ? (
            <div className="py-8 text-center text-xs text-gray-400">No matching issues found.</div>
          ) : (
            <div className="space-y-1">
              <div className="px-3 py-1 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
                {searchTerm ? 'Search Results' : 'Recent Work Items'}
              </div>
              {results.map(issue => (
                <div
                  key={issue.id}
                  onClick={() => {
                    openIssueDetail(issue.id);
                    onClose();
                  }}
                  className="flex items-center justify-between p-2.5 rounded-lg hover:bg-[#F4F5F7] cursor-pointer transition group"
                >
                  <div className="flex items-center space-x-3 min-w-0">
                    <TypeIcon type={issue.type} />
                    <span className="text-xs font-semibold text-[#0052CC] shrink-0">{issue.key}</span>
                    <span className="text-xs text-gray-800 truncate">{issue.summary}</span>
                  </div>

                  <div className="flex items-center space-x-3 shrink-0 ml-4">
                    <StatusBadge status={issue.status} />
                    <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-gray-600 transition" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 flex items-center justify-between text-[11px] text-gray-400">
          <span>Tip: Type project key and number for direct navigation</span>
          <span>{results.length} items found</span>
        </div>
      </div>
    </div>
  );
};

