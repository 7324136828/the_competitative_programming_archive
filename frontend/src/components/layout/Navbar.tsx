import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, 
  Bell, 
  Plus, 
  ChevronDown, 
  Check, 
  Layers, 
  UserCheck, 
  ShieldAlert,
  HelpCircle,
  ExternalLink,
  Bot,
  Settings,
  BookOpen
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext.js';
import { useProject } from '../../context/ProjectContext.js';
import { api } from '../../api/client.js';
import { getModelOverride, setModelOverride, onModelChange } from '../../utils/modelPreference.js';
import { Notification } from '../../types/index.js';
import { RoleBadge } from '../common/Badge.js';
import { X, Upload, Sparkles } from 'lucide-react';

interface NavbarProps {
  onOpenSearch: () => void;
  onOpenSettings: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenSearch, onOpenSettings }) => {
  const { currentUser, users, switchUser, isAdmin, isViewer, refreshUsers } = useAuth();
  const { projects, currentProject, switchProject, openCreateModal, openIssueDetail, reloadProjects, openImportStories, openAiStory, openLoadStudySet } = useProject();

  const [isProjectDropdownOpen, setIsProjectDropdownOpen] = useState(false);
  const [isPersonaDropdownOpen, setIsPersonaDropdownOpen] = useState(false);
  const [isNotifDropdownOpen, setIsNotifDropdownOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);

  // AI model selector
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [serverModel, setServerModel] = useState<string>('');
  const [aiModels, setAiModels] = useState<string[]>([]);
  const [modelOverride, setModelOverrideState] = useState<string | null>(getModelOverride());

  // Admin modals
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [projForm, setProjForm] = useState({ key: '', name: '', description: '' });
  const [projError, setProjError] = useState<string | null>(null);
  const [isMemberModalOpen, setIsMemberModalOpen] = useState(false);
  const [memberForm, setMemberForm] = useState({ name: '', email: '', role: 'Member' });
  const [memberError, setMemberError] = useState<string | null>(null);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    setProjError(null);
    try {
      const created = await api.createProject({
        key: projForm.key.trim(),
        name: projForm.name.trim(),
        description: projForm.description.trim(),
      });
      setIsProjectModalOpen(false);
      setProjForm({ key: '', name: '', description: '' });
      await reloadProjects(created.id);
    } catch (err: any) {
      setProjError(err.message);
    }
  };

  const handleCreateMember = async (e: React.FormEvent) => {
    e.preventDefault();
    setMemberError(null);
    try {
      await api.createUser({
        name: memberForm.name.trim(),
        email: memberForm.email.trim(),
        role: memberForm.role,
      });
      setIsMemberModalOpen(false);
      setMemberForm({ name: '', email: '', role: 'Member' });
      await refreshUsers();
    } catch (err: any) {
      setMemberError(err.message);
    }
  };

  const notifRef = useRef<HTMLDivElement>(null);
  const personaRef = useRef<HTMLDivElement>(null);
  const projectRef = useRef<HTMLDivElement>(null);
  const modelRef = useRef<HTMLDivElement>(null);

  const fetchNotifs = async () => {
    try {
      const data = await api.getNotifications();
      setNotifications(data);
    } catch (e) {}
  };

  const fetchAiStatus = async () => {
    try {
      const s = await api.getAiStatus();
      const models = Array.isArray(s.models)
        ? s.models.filter((model: unknown): model is string => typeof model === 'string' && model.length > 0)
        : [];
      const selected = models.includes(s.model) ? s.model : (models[0] || '');
      setServerModel(selected);
      setAiModels(models);
      const storedOverride = getModelOverride();
      if (storedOverride && !models.includes(storedOverride)) {
        setModelOverride(null);
        setModelOverrideState(null);
      }
    } catch (e) {}
  };

  useEffect(() => {
    fetchAiStatus();
    return onModelChange(() => setModelOverrideState(getModelOverride()));
  }, []);

  const handleSelectModel = async (model: string | null) => {
    setModelOverride(model);
    setModelOverrideState(model);
    setIsModelDropdownOpen(false);
    // Admins also persist the choice as the server-wide default so
    // server-side features (intake webhook, tools) use it too.
    if (isAdmin && model) {
      try {
        const out = await api.updateAiSettings(model);
        setServerModel(out.model);
      } catch (e) {}
    }
  };

  useEffect(() => {
    fetchNotifs();
    const interval = setInterval(fetchNotifs, 10000);
    return () => clearInterval(interval);
  }, [currentUser]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setIsNotifDropdownOpen(false);
      }
      if (personaRef.current && !personaRef.current.contains(e.target as Node)) {
        setIsPersonaDropdownOpen(false);
      }
      if (projectRef.current && !projectRef.current.contains(e.target as Node)) {
        setIsProjectDropdownOpen(false);
      }
      if (modelRef.current && !modelRef.current.contains(e.target as Node)) {
        setIsModelDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const unreadCount = notifications.filter(n => !n.is_read).length;

  const handleNotificationClick = async (notif: Notification) => {
    if (!notif.is_read) {
      await api.markNotificationRead(notif.id);
      fetchNotifs();
    }
    if (notif.issue_id) {
      openIssueDetail(notif.issue_id);
      setIsNotifDropdownOpen(false);
    }
  };

  return (
    <header className="h-14 bg-white border-b border-[#DFE1E6] px-4 flex items-center justify-between select-none z-30 relative">
      {/* Left: Jira branding & Project Selector */}
      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-2 cursor-pointer">
          <div className="w-8 h-8 rounded bg-[#0052CC] flex items-center justify-center text-white font-bold text-lg shadow-sm">
            J
          </div>
          <span className="font-bold text-[#172B4D] text-lg tracking-tight">Jira Software</span>
        </div>

        {/* Project Selector */}
        <div className="relative" ref={projectRef}>
          <button
            onClick={() => setIsProjectDropdownOpen(!isProjectDropdownOpen)}
            className="flex items-center space-x-2 px-3 py-1.5 rounded hover:bg-[#EBECF0] transition text-sm font-medium text-[#172B4D]"
          >
            <span>Projects</span>
            <span className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded border border-blue-200">
              {currentProject?.key || 'PROJ'}
            </span>
            <ChevronDown className="w-4 h-4 text-gray-500" />
          </button>

          {isProjectDropdownOpen && (
            <div className="absolute left-0 mt-1 w-64 bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="px-3 py-1.5 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
                Recent Projects
              </div>
              {projects.map(p => (
                <button
                  key={p.id}
                  onClick={() => {
                    switchProject(p.id);
                    setIsProjectDropdownOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between hover:bg-[#F4F5F7] transition ${
                    currentProject?.id === p.id ? 'bg-blue-50/50 text-[#0052CC] font-medium' : 'text-[#172B4D]'
                  }`}
                >
                  <div className="flex items-center space-x-2">
                    <div className="w-6 h-6 rounded bg-indigo-600 text-white flex items-center justify-center text-xs font-bold">
                      {p.key.substring(0, 2)}
                    </div>
                    <div>
                      <div className="font-medium text-xs leading-none">{p.name}</div>
                      <div className="text-[11px] text-gray-400 mt-0.5">Software project</div>
                    </div>
                  </div>
                  {currentProject?.id === p.id && <Check className="w-4 h-4 text-[#0052CC]" />}
                </button>
              ))}
              {isAdmin && (
                <button
                  onClick={() => {
                    setIsProjectDropdownOpen(false);
                    setProjError(null);
                    setIsProjectModalOpen(true);
                  }}
                  className="w-full text-left px-3 py-2 text-xs font-semibold text-[#0052CC] hover:bg-blue-50 border-t border-gray-100 flex items-center space-x-2"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Create project</span>
                </button>
              )}
            </div>
          )}
        </div>

        {/* Create Issue Action (J-01 / J-21) */}
        <button
          onClick={() => openCreateModal()}
          disabled={isViewer}
          className={`flex items-center space-x-1 px-3 py-1.5 rounded text-sm font-semibold shadow-sm transition ${
            isViewer
              ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
              : 'bg-[#0052CC] hover:bg-[#0065FF] text-white'
          }`}
          title={isViewer ? 'Viewer role cannot create issues' : 'Create new work item'}
        >
          <Plus className="w-4 h-4" />
          <span>Create</span>
        </button>

        {/* Import Problems Button */}
        <button
          onClick={openImportStories}
          className="flex items-center space-x-1 px-2.5 py-1.5 rounded text-xs font-semibold bg-white hover:bg-gray-100 border border-gray-300 text-gray-700 shadow-xs transition"
          title="Import problems without creating stories"
        >
          <Upload className="w-3.5 h-3.5 text-blue-600" />
          <span className="hidden md:inline">Import</span>
        </button>

        {/* AI Story Generator Button */}
        <button
          onClick={openAiStory}
          className="flex items-center space-x-1 px-2.5 py-1.5 rounded text-xs font-semibold bg-gradient-to-r from-amber-500 to-indigo-600 hover:from-amber-600 hover:to-indigo-700 text-white shadow-xs transition"
          title="Generate coding, learning, or non-coding story with AI"
        >
          <Sparkles className="w-3.5 h-3.5 text-amber-200" />
          <span className="hidden md:inline">AI Story</span>
        </button>

        {/* Load Study Set Button */}
        <button
          onClick={openLoadStudySet}
          className="flex items-center space-x-1 px-2.5 py-1.5 rounded text-xs font-semibold bg-emerald-50 hover:bg-emerald-100 border border-emerald-300 text-emerald-700 shadow-xs transition"
          title="Load and switch Study Sets"
        >
          <BookOpen className="w-3.5 h-3.5 text-emerald-600" />
          <span className="hidden md:inline">Study Set</span>
        </button>
      </div>

      {/* Middle: Quick Search trigger */}
      <div className="flex-1 max-w-md mx-6">
        <div
          onClick={onOpenSearch}
          className="flex items-center space-x-2 px-3 py-1.5 bg-[#FAFBFC] hover:bg-[#EBECF0] border border-[#DFE1E6] rounded-md cursor-pointer transition text-gray-500 text-sm group"
        >
          <Search className="w-4 h-4 group-hover:text-gray-700" />
          <span className="flex-1 text-xs">Search issues, summary, or key...</span>
          <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] bg-white border border-gray-300 rounded text-gray-500 font-mono shadow-xs">
            Ctrl+K
          </kbd>
        </div>
      </div>

      {/* Right: AI Model, Notifications & User Persona Switcher */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onOpenSettings}
          className="p-2 rounded-full hover:bg-[#EBECF0] text-gray-600 transition"
          title="Settings"
          aria-label="Settings"
        >
          <Settings className="w-5 h-5" />
        </button>

        {/* AI Model Selector */}
        <div className="relative" ref={modelRef}>
          <button
            onClick={() => {
              setIsModelDropdownOpen(!isModelDropdownOpen);
              if (!isModelDropdownOpen) fetchAiStatus();
            }}
            className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md hover:bg-[#EBECF0] transition text-xs font-medium text-[#172B4D] border border-gray-200"
            title="Choose the AI model used for AI features"
          >
            <Bot className="w-4 h-4 text-[#0052CC]" />
            <span className="max-w-[130px] truncate hidden lg:inline">
              {modelOverride || serverModel || 'AI model'}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          </button>

          {isModelDropdownOpen && (
            <div className="absolute right-0 mt-1 w-72 bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="px-3 py-1.5 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
                AI Model
              </div>
              <button
                onClick={() => handleSelectModel(null)}
                className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-[#F4F5F7] transition ${
                  !modelOverride ? 'bg-blue-50/50 text-[#0052CC] font-semibold' : 'text-[#172B4D]'
                }`}
              >
                <div>
                  <div className="font-medium">Server default</div>
                  <div className="text-[10px] text-gray-400 mt-0.5 font-mono">{serverModel || 'loading…'}</div>
                </div>
                {!modelOverride && <Check className="w-4 h-4 text-[#0052CC]" />}
              </button>
              <div className="border-t border-gray-100 my-1" />
              {aiModels.length === 0 && (
                <div className="px-3 py-2 text-[11px] text-gray-400">
                  No models reported by the Connector.
                </div>
              )}
              {aiModels.map(m => (
                <button
                  key={m}
                  onClick={() => handleSelectModel(m)}
                  className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-[#F4F5F7] transition ${
                    modelOverride === m ? 'bg-blue-50/50 text-[#0052CC] font-semibold' : 'text-[#172B4D]'
                  }`}
                >
                  <span className="font-mono truncate">{m}</span>
                  {modelOverride === m && <Check className="w-4 h-4 text-[#0052CC] flex-shrink-0" />}
                </button>
              ))}
              <div className="px-3 py-1.5 border-t border-gray-100 text-[10px] text-gray-400">
                {isAdmin
                  ? 'Your pick is also saved as the server-wide default.'
                  : 'Applies to AI requests from this browser.'}
              </div>
            </div>
          )}
        </div>

        {/* Watcher Notification Bell (J-11) */}
        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setIsNotifDropdownOpen(!isNotifDropdownOpen)}
            className="p-2 rounded-full hover:bg-[#EBECF0] text-gray-600 relative transition"
            title="Watcher Notifications (J-11)"
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white rounded-full text-[10px] font-bold flex items-center justify-center animate-pulse">
                {unreadCount}
              </span>
            )}
          </button>

          {isNotifDropdownOpen && (
            <div className="absolute right-0 mt-2 w-80 bg-white rounded-lg shadow-2xl border border-gray-200 py-2 z-50 max-h-96 overflow-y-auto animate-in fade-in zoom-in-95 duration-100">
              <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between">
                <span className="font-semibold text-xs text-gray-700">Notifications</span>
                <span className="text-[11px] text-gray-400">{unreadCount} unread</span>
              </div>
              {notifications.length === 0 ? (
                <div className="px-4 py-6 text-center text-xs text-gray-400">
                  No notifications yet. Watch an issue to receive updates!
                </div>
              ) : (
                notifications.map(n => (
                  <div
                    key={n.id}
                    onClick={() => handleNotificationClick(n)}
                    className={`px-4 py-2.5 hover:bg-[#F4F5F7] cursor-pointer transition border-b border-gray-50 ${
                      !n.is_read ? 'bg-blue-50/50' : ''
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-[#172B4D]">{n.title}</span>
                      <span className="text-[10px] text-gray-400">{n.issue_key}</span>
                    </div>
                    <p className="text-xs text-gray-600 mt-0.5 line-clamp-2">{n.message}</p>
                    <span className="text-[10px] text-gray-400 mt-1 block">
                      {new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* User Persona Switcher (J-21) */}
        <div className="relative" ref={personaRef}>
          <button
            onClick={() => setIsPersonaDropdownOpen(!isPersonaDropdownOpen)}
            className="flex items-center space-x-2 pl-2 pr-3 py-1 rounded-full hover:bg-[#EBECF0] transition border border-transparent hover:border-gray-200"
            title="Switch User Persona to test Roles and Permissions (J-21)"
          >
            <img
              src={currentUser?.avatar || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=faces'}
              alt={currentUser?.name}
              className="w-7 h-7 rounded-full object-cover border border-gray-300"
            />
            <div className="text-left hidden md:block">
              <div className="text-xs font-semibold text-[#172B4D] leading-none">{currentUser?.name}</div>
              <div className="text-[10px] text-gray-500 mt-0.5 flex items-center space-x-1">
                <RoleBadge role={currentUser?.role || 'Member'} />
              </div>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          </button>

          {isPersonaDropdownOpen && (
            <div className="absolute right-0 mt-1 w-64 bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="px-3 py-1.5 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
                Simulate User Persona (J-21)
              </div>
              {users.map(u => (
                <button
                  key={u.id}
                  onClick={() => {
                    switchUser(u.id);
                    setIsPersonaDropdownOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-[#F4F5F7] transition ${
                    currentUser?.id === u.id ? 'bg-blue-50/50 text-[#0052CC] font-semibold' : 'text-[#172B4D]'
                  }`}
                >
                  <div className="flex items-center space-x-2">
                    <img src={u.avatar} alt={u.name} className="w-6 h-6 rounded-full object-cover" />
                    <div>
                      <div className="font-medium leading-none">{u.name}</div>
                      <div className="text-[10px] text-gray-400 mt-0.5">{u.email}</div>
                    </div>
                  </div>
                  <RoleBadge role={u.role} />
                </button>
              ))}
              {isAdmin && (
                <button
                  onClick={() => {
                    setIsPersonaDropdownOpen(false);
                    setMemberError(null);
                    setIsMemberModalOpen(true);
                  }}
                  className="w-full text-left px-3 py-2 text-xs font-semibold text-[#0052CC] hover:bg-blue-50 border-t border-gray-100 flex items-center space-x-2"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add team member</span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Create Project Modal (Admin) */}
      {isProjectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <form onSubmit={handleCreateProject} className="bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-md p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-[#172B4D]">Create project</h2>
              <button type="button" onClick={() => setIsProjectModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
            {projError && <div className="p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">{projError}</div>}
            <div>
              <label className="block text-[11px] font-bold text-gray-500 uppercase mb-1">Key *</label>
              <input
                value={projForm.key}
                onChange={e => setProjForm(f => ({ ...f, key: e.target.value.toUpperCase() }))}
                placeholder="e.g. WEB"
                maxLength={10}
                required
                className="w-full px-3 py-1.5 border border-gray-300 rounded text-xs outline-none focus:ring-1 focus:ring-blue-500 font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-500 uppercase mb-1">Name *</label>
              <input
                value={projForm.name}
                onChange={e => setProjForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Web Platform"
                required
                className="w-full px-3 py-1.5 border border-gray-300 rounded text-xs outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-500 uppercase mb-1">Description</label>
              <textarea
                value={projForm.description}
                onChange={e => setProjForm(f => ({ ...f, description: e.target.value }))}
                rows={2}
                className="w-full px-3 py-1.5 border border-gray-300 rounded text-xs outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div className="flex justify-end space-x-2">
              <button type="button" onClick={() => setIsProjectModalOpen(false)} className="px-3 py-1.5 text-xs text-gray-600">Cancel</button>
              <button type="submit" disabled={!projForm.key.trim() || !projForm.name.trim()}
                className="px-4 py-1.5 bg-[#0052CC] text-white text-xs font-semibold rounded hover:bg-[#0065FF] disabled:opacity-50">
                Create project
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Add Team Member Modal (Admin) */}
      {isMemberModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <form onSubmit={handleCreateMember} className="bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-md p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-[#172B4D]">Add team member</h2>
              <button type="button" onClick={() => setIsMemberModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
            {memberError && <div className="p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">{memberError}</div>}
            <div>
              <label className="block text-[11px] font-bold text-gray-500 uppercase mb-1">Name *</label>
              <input
                value={memberForm.name}
                onChange={e => setMemberForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Jamie Doe"
                required
                className="w-full px-3 py-1.5 border border-gray-300 rounded text-xs outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-500 uppercase mb-1">Email *</label>
              <input
                type="email"
                value={memberForm.email}
                onChange={e => setMemberForm(f => ({ ...f, email: e.target.value }))}
                placeholder="jamie@company.com"
                required
                className="w-full px-3 py-1.5 border border-gray-300 rounded text-xs outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-500 uppercase mb-1">Role</label>
              <select
                value={memberForm.role}
                onChange={e => setMemberForm(f => ({ ...f, role: e.target.value }))}
                className="w-full px-3 py-1.5 border border-gray-300 rounded text-xs bg-white outline-none"
              >
                <option value="Admin">Admin</option>
                <option value="Member">Member</option>
                <option value="Viewer">Viewer</option>
              </select>
            </div>
            <div className="flex justify-end space-x-2">
              <button type="button" onClick={() => setIsMemberModalOpen(false)} className="px-3 py-1.5 text-xs text-gray-600">Cancel</button>
              <button type="submit" disabled={!memberForm.name.trim() || !memberForm.email.trim()}
                className="px-4 py-1.5 bg-[#0052CC] text-white text-xs font-semibold rounded hover:bg-[#0065FF] disabled:opacity-50">
                Add member
              </button>
            </div>
          </form>
        </div>
      )}
    </header>
  );
};

