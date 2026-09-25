import React, { useState, useEffect } from 'react';
import {
  Workflow,
  Zap,
  Sliders,
  ShieldCheck,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  ToggleLeft,
  ToggleRight,
  Clock,
  ArrowRight,
  Database,
  Loader2
} from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { useAuth } from '../../context/AuthContext.js';
import { api } from '../../api/client.js';
import { 
  AutomationRule, 
  AutomationLog, 
  WorkflowTransition, 
  WorkflowStatus,
  CustomFieldValue 
} from '../../types/index.js';
import { RoleBadge } from '../common/Badge.js';

export const ProjectSettingsView: React.FC = () => {
  const { currentProject, triggerRefresh, refreshKey, reloadProjects } = useProject();
  const { users, isAdmin, refreshUsers } = useAuth();

  const [activeTab, setActiveTab] = useState<'workflows' | 'automation' | 'customFields' | 'permissions' | 'database'>('automation');
  const [purgeConfirmation, setPurgeConfirmation] = useState('');
  const [isPurging, setIsPurging] = useState(false);
  const [purgeError, setPurgeError] = useState<string | null>(null);
  const [purgeNotice, setPurgeNotice] = useState<string | null>(null);

  // Workflows (J-20)
  const [workflow, setWorkflow] = useState<any>(null);
  const [statuses, setStatuses] = useState<WorkflowStatus[]>([]);
  const [transitions, setTransitions] = useState<WorkflowTransition[]>([]);
  const [newFromStatus, setNewFromStatus] = useState('In Progress');
  const [newToStatus, setNewToStatus] = useState('In Review');
  const [newTransitionName, setNewTransitionName] = useState('');

  // Automation (J-22)
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [logs, setLogs] = useState<AutomationLog[]>([]);
  const [isCreatingRule, setIsCreatingRule] = useState(false);
  const [ruleName, setRuleName] = useState('');
  const [triggerEvent, setTriggerEvent] = useState('ISSUE_CREATED');
  const [condField, setCondField] = useState('type');
  const [condValue, setCondValue] = useState('Bug');
  const [actionType, setActionType] = useState('assign');
  const [actionTarget, setActionTarget] = useState('');

  // Custom Fields (J-19)
  const [customFields, setCustomFields] = useState<any[]>([]);
  const [newCfName, setNewCfName] = useState('');
  const [newCfType, setNewCfType] = useState('select');
  const [newCfOptions, setNewCfOptions] = useState('Critical, High, Medium, Low');
  const [isAddingCf, setIsAddingCf] = useState(false);

  const loadSettingsData = async () => {
    if (!currentProject) return;
    try {
      const [wfData, rulesData, logsData, cfData] = await Promise.all([
        api.getWorkflow(currentProject.id),
        api.getAutomationRules(currentProject.id),
        api.getAutomationLogs(currentProject.id),
        api.getCustomFields(currentProject.id),
      ]);

      setWorkflow(wfData.workflow);
      setStatuses(wfData.statuses || []);
      setTransitions(wfData.transitions || []);
      setRules(rulesData);
      setLogs(logsData);
      setCustomFields(cfData);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadSettingsData();
  }, [currentProject, refreshKey]);

  // J-20: Add workflow transition
  const handleAddTransition = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workflow || !newTransitionName.trim()) return;
    try {
      await api.addTransition({
        workflowId: workflow.id,
        fromStatus: newFromStatus,
        toStatus: newToStatus,
        name: newTransitionName.trim(),
      });
      setNewTransitionName('');
      loadSettingsData();
      triggerRefresh();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleDeleteTransition = async (id: string) => {
    try {
      await api.deleteTransition(id);
      loadSettingsData();
      triggerRefresh();
    } catch (err: any) {
      alert(err.message);
    }
  };

  // J-22: Create automation rule
  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleName.trim()) return;
    try {
      await api.createAutomationRule({
        projectId: currentProject?.id,
        name: ruleName.trim(),
        triggerEvent,
        conditions: [{ field: condField, operator: 'equals', value: condValue }],
        actions: [{ action: actionType, target: actionTarget }],
        isEnabled: 1,
      });
      setIsCreatingRule(false);
      setRuleName('');
      loadSettingsData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleToggleRule = async (ruleId: string) => {
    try {
      await api.toggleAutomationRule(ruleId);
      loadSettingsData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      await api.deleteAutomationRule(ruleId);
      loadSettingsData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  // J-19: Add custom field
  const handleAddCustomField = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentProject || !newCfName.trim()) return;
    try {
      const options = newCfType === 'select'
        ? newCfOptions.split(',').map(s => s.trim()).filter(Boolean)
        : null;

      await api.createCustomField(currentProject.id, {
        name: newCfName.trim(),
        fieldType: newCfType,
        options,
      });
      setIsAddingCf(false);
      setNewCfName('');
      loadSettingsData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handlePurgeDatabase = async () => {
    if (!isAdmin || purgeConfirmation !== 'PURGE' || isPurging) return;
    setIsPurging(true);
    setPurgeError(null);
    setPurgeNotice(null);
    try {
      const result = await api.purgeDatabase(purgeConfirmation);
      setPurgeConfirmation('');
      localStorage.removeItem('jira_active_project_id');
      await Promise.all([refreshUsers(), reloadProjects()]);
      setPurgeNotice(result.message);
    } catch (err: any) {
      setPurgeError(err.message);
    } finally {
      setIsPurging(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-[#172B4D]">Project Settings & Customization</h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Configure project workflows (J-20), custom fields (J-19), automation rules (J-22), and access control (J-21)
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center space-x-2 border-b border-gray-200">
        <button
          onClick={() => setActiveTab('automation')}
          className={`pb-2.5 px-3 text-xs font-semibold flex items-center space-x-2 border-b-2 transition ${
            activeTab === 'automation'
              ? 'border-[#0052CC] text-[#0052CC]'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Zap className="w-4 h-4 text-amber-500" />
          <span>Automation Rules (J-22)</span>
        </button>

        <button
          onClick={() => setActiveTab('workflows')}
          className={`pb-2.5 px-3 text-xs font-semibold flex items-center space-x-2 border-b-2 transition ${
            activeTab === 'workflows'
              ? 'border-[#0052CC] text-[#0052CC]'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Workflow className="w-4 h-4 text-blue-600" />
          <span>Workflow Transitions (J-20)</span>
        </button>

        <button
          onClick={() => setActiveTab('customFields')}
          className={`pb-2.5 px-3 text-xs font-semibold flex items-center space-x-2 border-b-2 transition ${
            activeTab === 'customFields'
              ? 'border-[#0052CC] text-[#0052CC]'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Sliders className="w-4 h-4 text-purple-600" />
          <span>Custom Fields (J-19)</span>
        </button>

        <button
          onClick={() => setActiveTab('permissions')}
          className={`pb-2.5 px-3 text-xs font-semibold flex items-center space-x-2 border-b-2 transition ${
            activeTab === 'permissions'
              ? 'border-[#0052CC] text-[#0052CC]'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          <span>Permissions & Team (J-21)</span>
        </button>

        <button
          onClick={() => setActiveTab('database')}
          className={`pb-2.5 px-3 text-xs font-semibold flex items-center space-x-2 border-b-2 transition ${
            activeTab === 'database'
              ? 'border-red-600 text-red-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Database className="w-4 h-4" />
          <span>Database</span>
        </button>
      </div>

      {/* TAB 1: AUTOMATION (J-22) */}
      {activeTab === 'automation' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-gray-800">Jira Automation Engine</h2>
              <p className="text-xs text-gray-500">Automate triage, assignment, and status routing when triggers fire</p>
            </div>
            {isAdmin && (
              <button
                onClick={() => setIsCreatingRule(true)}
                className="px-3 py-1.5 bg-[#0052CC] hover:bg-[#0065FF] text-white rounded-md text-xs font-semibold shadow-xs flex items-center space-x-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Create rule</span>
              </button>
            )}
          </div>

          {/* Create Rule Form */}
          {isCreatingRule && (
            <form onSubmit={handleCreateRule} className="p-5 bg-white rounded-xl border border-blue-200 shadow-sm space-y-4 text-xs animate-in fade-in duration-100">
              <div className="font-bold text-sm text-blue-900">Configure Automation Rule</div>
              <input
                type="text"
                required
                autoFocus
                value={ruleName}
                onChange={e => setRuleName(e.target.value)}
                placeholder="Rule Name (e.g. Auto-assign High Priority Bugs)"
                className="w-full px-3 py-1.5 border border-gray-300 rounded outline-none"
              />

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block font-semibold text-gray-700 mb-1">When (Trigger):</label>
                  <select
                    value={triggerEvent}
                    onChange={e => setTriggerEvent(e.target.value)}
                    className="w-full px-2 py-1.5 border border-gray-300 rounded bg-white"
                  >
                    <option value="ISSUE_CREATED">Issue Created</option>
                    <option value="STATUS_CHANGED">Status Changed</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-gray-700 mb-1">If (Condition):</label>
                  <div className="flex space-x-1">
                    <select
                      value={condField}
                      onChange={e => setCondField(e.target.value)}
                      className="w-1/2 px-1 py-1.5 border border-gray-300 rounded bg-white text-[11px]"
                    >
                      <option value="type">Type ==</option>
                      <option value="priority">Priority ==</option>
                    </select>
                    <input
                      type="text"
                      value={condValue}
                      onChange={e => setCondValue(e.target.value)}
                      className="w-1/2 px-2 py-1.5 border border-gray-300 rounded text-[11px]"
                      placeholder="Bug"
                    />
                  </div>
                </div>

                <div>
                  <label className="block font-semibold text-gray-700 mb-1">Then (Action):</label>
                  <select
                    value={actionTarget}
                    onChange={e => setActionTarget(e.target.value)}
                    className="w-full px-2 py-1.5 border border-gray-300 rounded bg-white"
                  >
                    <option value="">Select user...</option>
                    {users.filter(u => u.role !== 'Viewer').map(u => (
                      <option key={u.id} value={u.id}>Assign to {u.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex justify-end space-x-2 pt-2 border-t border-gray-100">
                <button type="button" onClick={() => setIsCreatingRule(false)} className="px-3 py-1 text-gray-500">Cancel</button>
                <button type="submit" className="px-3 py-1 bg-[#0052CC] text-white font-semibold rounded hover:bg-[#0065FF]">Save Rule</button>
              </div>
            </form>
          )}

          {/* Rules List */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-xs divide-y divide-gray-100">
            {rules.map(rule => (
              <div key={rule.id} className="p-4 flex items-center justify-between text-xs">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center font-bold">
                    <Zap className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-semibold text-gray-900">{rule.name}</div>
                    <div className="text-[11px] text-gray-500 mt-0.5">
                      Trigger: <span className="font-mono text-gray-700">{rule.trigger_event}</span> • Conditions: <span className="font-mono">{rule.conditions_json}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-4">
                  <button
                    onClick={() => handleToggleRule(rule.id)}
                    className="flex items-center space-x-1.5 text-xs font-semibold text-gray-600"
                  >
                    {rule.is_enabled ? (
                      <span className="flex items-center text-emerald-600 space-x-1">
                        <ToggleRight className="w-5 h-5 text-emerald-600" />
                        <span>Enabled</span>
                      </span>
                    ) : (
                      <span className="flex items-center text-gray-400 space-x-1">
                        <ToggleLeft className="w-5 h-5 text-gray-400" />
                        <span>Disabled</span>
                      </span>
                    )}
                  </button>

                  {isAdmin && (
                    <button onClick={() => handleDeleteRule(rule.id)} className="text-gray-400 hover:text-red-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Execution Audit Logs (J-22 acceptance criterion) */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <div className="flex items-center space-x-2">
                <Clock className="w-4 h-4 text-gray-500" />
                <h3 className="font-bold text-xs text-gray-800 uppercase tracking-wider">
                  Rule Execution Audit Log (J-22)
                </h3>
              </div>
              <span className="text-[11px] text-gray-400 font-mono">{logs.length} logged runs</span>
            </div>

            <div className="divide-y divide-gray-100 max-h-72 overflow-y-auto">
              {logs.map(log => (
                <div key={log.id} className="py-2.5 flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-3">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        log.status === 'SUCCESS'
                          ? 'bg-emerald-100 text-emerald-800'
                          : (log.status === 'SKIPPED' ? 'bg-gray-100 text-gray-600' : 'bg-red-100 text-red-800')
                      }`}
                    >
                      {log.status}
                    </span>
                    <span className="font-semibold text-gray-800">{log.rule_name}</span>
                    {log.issue_key && (
                      <span className="font-mono text-[#0052CC] font-semibold">{log.issue_key}</span>
                    )}
                    <span className="text-gray-500 truncate max-w-md">{log.details}</span>
                  </div>
                  <span className="text-[10px] text-gray-400 font-mono">
                    {new Date(log.executed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
              ))}
              {logs.length === 0 && (
                <div className="py-6 text-center text-xs text-gray-400">No execution logs yet.</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: WORKFLOW TRANSITIONS (J-20) */}
      {activeTab === 'workflows' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-bold text-gray-800">Workflow Transitions Designer (J-20)</h2>
            <p className="text-xs text-gray-500">
              Configure allowed state transitions. Items cannot move to a status unless a transition is explicitly permitted.
            </p>
          </div>

          {/* Add Transition Form */}
          {isAdmin && (
            <form onSubmit={handleAddTransition} className="p-4 bg-white rounded-xl border border-blue-200 shadow-xs space-y-3 text-xs">
              <div className="font-bold text-blue-900">Add Permitted Transition (J-20)</div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block font-semibold text-gray-700 mb-1">From Status:</label>
                  <select
                    value={newFromStatus}
                    onChange={e => setNewFromStatus(e.target.value)}
                    className="w-full px-2 py-1.5 border border-gray-300 rounded bg-white"
                  >
                    {statuses.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-gray-700 mb-1">To Status:</label>
                  <select
                    value={newToStatus}
                    onChange={e => setNewToStatus(e.target.value)}
                    className="w-full px-2 py-1.5 border border-gray-300 rounded bg-white"
                  >
                    {statuses.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-gray-700 mb-1">Transition Action Name:</label>
                  <input
                    type="text"
                    required
                    value={newTransitionName}
                    onChange={e => setNewTransitionName(e.target.value)}
                    placeholder="e.g. Fast Track / Submit"
                    className="w-full px-3 py-1.5 border border-gray-300 rounded"
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <button type="submit" className="px-3 py-1 bg-[#0052CC] text-white font-semibold rounded hover:bg-[#0065FF]">
                  Add Transition
                </button>
              </div>
            </form>
          )}

          {/* Configured Transitions List */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-xs divide-y divide-gray-100">
            {transitions.map(tr => (
              <div key={tr.id} className="p-3.5 flex items-center justify-between text-xs hover:bg-gray-50/50">
                <div className="flex items-center space-x-3">
                  <span className="font-bold text-gray-800">{tr.name}</span>
                  <div className="flex items-center space-x-2 text-gray-500 font-mono text-[11px]">
                    <span className="bg-gray-100 px-2 py-0.5 rounded font-semibold text-gray-700">{tr.from_status}</span>
                    <ArrowRight className="w-3.5 h-3.5 text-gray-400" />
                    <span className="bg-blue-50 px-2 py-0.5 rounded font-semibold text-[#0052CC]">{tr.to_status}</span>
                  </div>
                </div>

                {isAdmin && (
                  <button onClick={() => handleDeleteTransition(tr.id)} className="text-gray-400 hover:text-red-600 p-1">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 3: CUSTOM FIELDS (J-19) */}
      {activeTab === 'customFields' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-gray-800">Project Custom Fields (J-19)</h2>
              <p className="text-xs text-gray-500">Capture business information missing from default fields</p>
            </div>
            {isAdmin && (
              <button
                onClick={() => setIsAddingCf(true)}
                className="px-3 py-1.5 bg-[#0052CC] hover:bg-[#0065FF] text-white rounded-md text-xs font-semibold shadow-xs flex items-center space-x-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add custom field</span>
              </button>
            )}
          </div>

          {isAddingCf && (
            <form onSubmit={handleAddCustomField} className="p-4 bg-white rounded-xl border border-blue-200 shadow-sm space-y-3 text-xs">
              <div className="font-bold text-blue-900">New Custom Field Definition</div>
              <div className="grid grid-cols-3 gap-3">
                <input
                  type="text"
                  required
                  autoFocus
                  value={newCfName}
                  onChange={e => setNewCfName(e.target.value)}
                  placeholder="Field label (e.g. Customer Impact)"
                  className="px-3 py-1.5 border border-gray-300 rounded"
                />
                <select
                  value={newCfType}
                  onChange={e => setNewCfType(e.target.value)}
                  className="px-2 py-1.5 border border-gray-300 rounded bg-white"
                >
                  <option value="select">Dropdown Select</option>
                  <option value="text">Single-line Text</option>
                  <option value="number">Number</option>
                </select>
                {newCfType === 'select' && (
                  <input
                    type="text"
                    value={newCfOptions}
                    onChange={e => setNewCfOptions(e.target.value)}
                    placeholder="Comma-separated options..."
                    className="px-3 py-1.5 border border-gray-300 rounded"
                  />
                )}
              </div>
              <div className="flex justify-end space-x-2">
                <button type="button" onClick={() => setIsAddingCf(false)} className="px-3 py-1 text-gray-500">Cancel</button>
                <button type="submit" className="px-3 py-1 bg-[#0052CC] text-white font-semibold rounded">Save Field</button>
              </div>
            </form>
          )}

          <div className="bg-white rounded-xl border border-gray-200 shadow-xs divide-y divide-gray-100">
            {customFields.map(cf => (
              <div key={cf.id} className="p-4 flex items-center justify-between text-xs">
                <div>
                  <div className="font-semibold text-gray-900">{cf.name}</div>
                  <div className="text-[11px] text-gray-500 mt-0.5">
                    Type: <span className="font-mono text-gray-700">{cf.field_type}</span>
                    {cf.options_json && <span> • Options: {cf.options_json}</span>}
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200 font-mono">
                  {cf.id}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 4: PERMISSIONS & TEAM (J-21) */}
      {activeTab === 'permissions' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-bold text-gray-800">Role-Based Access Control (J-21)</h2>
            <p className="text-xs text-gray-500">
              Control editing and project administration. Viewers have read-only access and cannot edit or delete work items.
            </p>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-5 space-y-4">
            <h3 className="font-bold text-xs text-gray-800 uppercase tracking-wider">Role Permissions Matrix</h3>
            
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b border-gray-200 text-gray-400 uppercase text-[10px]">
                  <th className="pb-2">Capability</th>
                  <th className="pb-2">Admin</th>
                  <th className="pb-2">Member</th>
                  <th className="pb-2">Viewer (Guest)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                <tr>
                  <td className="py-2.5 font-medium text-gray-800">View work items & boards</td>
                  <td className="py-2.5 text-emerald-600 font-bold">✓ Allowed</td>
                  <td className="py-2.5 text-emerald-600 font-bold">✓ Allowed</td>
                  <td className="py-2.5 text-emerald-600 font-bold">✓ Allowed</td>
                </tr>
                <tr>
                  <td className="py-2.5 font-medium text-gray-800">Create & edit work items (J-01, J-21)</td>
                  <td className="py-2.5 text-emerald-600 font-bold">✓ Allowed</td>
                  <td className="py-2.5 text-emerald-600 font-bold">✓ Allowed</td>
                  <td className="py-2.5 text-red-500 font-bold">✗ Denied (403)</td>
                </tr>
                <tr>
                  <td className="py-2.5 font-medium text-gray-800">Transition status & rank backlog (J-05, J-08)</td>
                  <td className="py-2.5 text-emerald-600 font-bold">✓ Allowed</td>
                  <td className="py-2.5 text-emerald-600 font-bold">✓ Allowed</td>
                  <td className="py-2.5 text-red-500 font-bold">✗ Denied</td>
                </tr>
                <tr>
                  <td className="py-2.5 font-medium text-gray-800">Configure workflows & automation (J-20, J-22)</td>
                  <td className="py-2.5 text-emerald-600 font-bold">✓ Allowed</td>
                  <td className="py-2.5 text-red-500 font-bold">✗ Denied</td>
                  <td className="py-2.5 text-red-500 font-bold">✗ Denied</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Project Members List */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-xs divide-y divide-gray-100">
            <div className="px-5 py-3 bg-[#FAFBFC] font-bold text-xs text-gray-700">Project Members</div>
            {users.map(u => (
              <div key={u.id} className="p-3.5 flex items-center justify-between text-xs">
                <div className="flex items-center space-x-3">
                  <img src={u.avatar} alt={u.name} className="w-7 h-7 rounded-full object-cover" />
                  <div>
                    <div className="font-semibold text-gray-900">{u.name}</div>
                    <div className="text-[11px] text-gray-400">{u.email}</div>
                  </div>
                </div>
                <RoleBadge role={u.role} />
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'database' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-bold text-gray-800">Database administration</h2>
            <p className="text-xs text-gray-500">
              Permanently remove all projects, stories, problem sets, problems, submissions, and application history.
            </p>
          </div>

          <div className="bg-white rounded-xl border border-red-300 shadow-xs p-5 space-y-4">
            <div className="flex items-start space-x-3">
              <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-bold text-sm text-red-800">Danger zone</h3>
                <p className="text-xs text-gray-600 mt-1 leading-5">
                  This cannot be undone. Your current admin account and one empty default project will be recreated so you can continue using the app.
                </p>
              </div>
            </div>

            {!isAdmin ? (
              <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
                Only an Admin can purge the database.
              </div>
            ) : (
              <div className="max-w-lg space-y-3">
                <label htmlFor="purge-confirmation" className="block text-xs font-semibold text-gray-700">
                  Type <span className="font-mono text-red-700">PURGE</span> to confirm
                </label>
                <input
                  id="purge-confirmation"
                  value={purgeConfirmation}
                  onChange={event => setPurgeConfirmation(event.target.value)}
                  disabled={isPurging}
                  autoComplete="off"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono outline-none focus:ring-2 focus:ring-red-500 disabled:bg-gray-100"
                  placeholder="PURGE"
                />
                <button
                  type="button"
                  onClick={handlePurgeDatabase}
                  disabled={purgeConfirmation !== 'PURGE' || isPurging}
                  className="inline-flex items-center space-x-2 px-3 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white text-xs font-bold disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  {isPurging ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                  <span>{isPurging ? 'Purging database…' : 'Purge entire database'}</span>
                </button>
                {purgeError && <p className="text-xs text-red-700" role="alert">{purgeError}</p>}
                {purgeNotice && <p className="text-xs text-emerald-700" role="status">{purgeNotice}</p>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

