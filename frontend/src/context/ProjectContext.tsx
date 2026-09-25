import React, { createContext, useContext, useState, useEffect } from 'react';
import { Project, Issue } from '../types/index.js';
import { api } from '../api/client.js';

interface ProjectContextType {
  projects: Project[];
  currentProject: Project | null;
  switchProject: (projectId: string) => void;
  selectedIssueId: string | null;
  openIssueDetail: (issueId: string) => void;
  closeIssueDetail: () => void;
  isCreateModalOpen: boolean;
  openCreateModal: (defaultValues?: any) => void;
  closeCreateModal: () => void;
  createModalDefaults: any;
  activeActivityIssue: Issue | null;
  openActivity: (issue: Issue) => void;
  closeActivity: () => void;
  isImportStoriesOpen: boolean;
  openImportStories: () => void;
  closeImportStories: () => void;
  isAiStoryOpen: boolean;
  openAiStory: () => void;
  closeAiStory: () => void;
  refreshKey: number;
  triggerRefresh: () => void;
  isLoading: boolean;
  reloadProjects: (selectId?: string) => Promise<void>;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createModalDefaults, setCreateModalDefaults] = useState<any>(null);
  const [activeActivityIssue, setActiveActivityIssue] = useState<Issue | null>(null);
  const [isImportStoriesOpen, setIsImportStoriesOpen] = useState(false);
  const [isAiStoryOpen, setIsAiStoryOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  const fetchProjects = async (selectId?: string) => {
    try {
      const data = await api.getProjects();
      setProjects(data);
      if (data.length === 0) {
        setCurrentProject(null);
        return;
      }
      const wanted = selectId || localStorage.getItem('jira_active_project_id') || currentProject?.id;
      const match = data.find((p: Project) => p.id === wanted) || data[0];
      if (match.id !== currentProject?.id) {
        setCurrentProject(match);
        localStorage.setItem('jira_active_project_id', match.id);
      }
    } catch (e) {
      console.error('Failed to load projects:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, [refreshKey]);

  const reloadProjects = async (selectId?: string) => {
    await fetchProjects(selectId);
    triggerRefresh();
  };

  const switchProject = (projectId: string) => {
    const found = projects.find(p => p.id === projectId);
    if (found) {
      setCurrentProject(found);
      localStorage.setItem('jira_active_project_id', found.id);
      triggerRefresh();
    }
  };

  const triggerRefresh = () => setRefreshKey(k => k + 1);

  const openIssueDetail = (issueId: string) => setSelectedIssueId(issueId);
  const closeIssueDetail = () => setSelectedIssueId(null);

  const openCreateModal = (defaultValues?: any) => {
    setCreateModalDefaults(defaultValues || null);
    setIsCreateModalOpen(true);
  };
  const closeCreateModal = () => {
    setIsCreateModalOpen(false);
    setCreateModalDefaults(null);
  };
  const openActivity = (issue: Issue) => setActiveActivityIssue(issue);
  const closeActivity = () => setActiveActivityIssue(null);

  const openImportStories = () => setIsImportStoriesOpen(true);
  const closeImportStories = () => setIsImportStoriesOpen(false);

  const openAiStory = () => setIsAiStoryOpen(true);
  const closeAiStory = () => setIsAiStoryOpen(false);

  return (
    <ProjectContext.Provider
      value={{
        projects,
        currentProject,
        switchProject,
        selectedIssueId,
        openIssueDetail,
        closeIssueDetail,
        isCreateModalOpen,
        openCreateModal,
        closeCreateModal,
        createModalDefaults,
        activeActivityIssue,
        openActivity,
        closeActivity,
        isImportStoriesOpen,
        openImportStories,
        closeImportStories,
        isAiStoryOpen,
        openAiStory,
        closeAiStory,
        refreshKey,
        triggerRefresh,
        isLoading,
        reloadProjects,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = () => {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProject must be used within a ProjectProvider');
  return ctx;
};

