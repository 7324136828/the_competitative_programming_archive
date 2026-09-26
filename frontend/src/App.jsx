import React, { useState, useEffect } from 'react';
import { AuthProvider } from './context/AuthContext';
import { ProjectProvider, useProject } from './context/ProjectContext';
import { Navbar } from './components/layout/Navbar';
import { Sidebar } from './components/layout/Sidebar';
import { GlobalSearchModal } from './components/layout/GlobalSearchModal';
import { CreateIssueModal } from './components/issues/CreateIssueModal';
import { IssueDetailModal } from './components/issues/IssueDetailModal';
import { ImportStoriesModal } from './components/issues/ImportStoriesModal';
import { AiStoryModal } from './components/issues/AiStoryModal';
import { ActivityScreen } from './components/activity/ActivityScreen';

import { KanbanScrumBoard } from './components/board/KanbanScrumBoard';
import { BacklogView } from './components/backlog/BacklogView';
import { TimelineGanttView } from './components/timeline/TimelineGanttView';
import { CrossTeamPlanView } from './components/crossteam/CrossTeamPlanView';
import { ReleasesView } from './components/releases/ReleasesView';
import { SprintBurndownView } from './components/reports/SprintBurndownView';
import { DashboardView } from './components/dashboard/DashboardView';
import { IssuesFilterView } from './components/issues/IssuesFilterView';
import { ProjectSettingsView } from './components/settings/ProjectSettingsView';
import { MetricsView } from './components/metrics/MetricsView';
import { AiAssistantView } from './components/ai/AiAssistantView';
import ProblemList from './components/ProblemList';
import { StudySetApp } from './components/studyset/StudySetApp';
import { LoadStudySetModal } from './components/studyset/LoadStudySetModal';
import { fetchProblem } from './services/api';
import { api } from './api/client';

const VALID_TABS = [
  'board',
  'backlog',
  'problems',
  'studyset',
  'timeline',
  'crossteam',
  'releases',
  'burndown',
  'dashboard',
  'filters',
  'settings',
  'ai',
  'metrics'
];

const MainApp = () => {
  const [activeTab, setActiveTab] = useState(() => {
    const h = window.location.hash.replace(/^#/, '');
    return VALID_TABS.includes(h) ? h : 'board';
  });
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const {
    currentProject,
    activeActivityIssue,
    closeActivity,
    openActivity,
    openIssueDetail,
    isImportStoriesOpen,
    closeImportStories,
    isAiStoryOpen,
    closeAiStory,
    isLoadStudySetOpen,
    closeLoadStudySet,
    activeStudySetId,
    setActiveStudySetId,
    refreshKey,
    triggerRefresh,
  } = useProject();

  // Global search shortcut (Ctrl+K or Cmd+K)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setIsSearchOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Hash synchronization
  useEffect(() => {
    const onHashChange = () => {
      const h = window.location.hash.replace(/^#/, '');
      if (VALID_TABS.includes(h)) setActiveTab(h);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    if (window.location.hash !== `#${activeTab}`) {
      history.replaceState(null, '', `#${activeTab}`);
    }
  }, [activeTab]);

  useEffect(() => {
    api.logActivity('view', { view: activeTab });
  }, [activeTab]);

  // Open problem directly in Activity Screen
  const handleSelectProblemFromList = async (problemId) => {
    try {
      const res = await fetchProblem(problemId);
      if (res.success && res.problem) {
        const p = res.problem;
        if (p.story_id) {
          const linkedStory = await api.getIssue(p.story_id);
          openActivity(linkedStory);
          return;
        }
        openActivity({
          id: `problem-${p.id}`,
          key: `CP-${p.id}`,
          project_id: currentProject?.id || 'PROJ-1',
          project_key: currentProject?.key || 'CP',
          type: 'Story',
          story_type: 'coding',
          summary: p.title,
          description: p.problem_statements,
          difficulty: p.difficulty,
          problem_id: p.id,
          sample_input_output: p.sample_input_output || [],
          hints: p.hints || [],
          tags: p.tags || [],
          status: p.is_solved ? 'Done' : 'To Do',
          submission_status: p.is_solved ? 'Accepted' : undefined,
          rank: 0,
          priority: 'Medium',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }
    } catch (err) {
      console.error('Failed to load problem for activity screen:', err);
    }
  };

  const handleCreateStoryForProblem = async (problemId) => {
    if (!currentProject?.id) {
      throw new Error('Create or select a project before creating a story.');
    }
    const story = await api.ensureStoryForProblem(problemId, currentProject.id);
    triggerRefresh();
    return story;
  };

  const handleActivityStatusUpdated = (_issueId, _newStatus) => {
    triggerRefresh();
  };

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-[#F4F5F7]">
      {/* Top Navigation */}
      <Navbar
        onOpenSearch={() => setIsSearchOpen(true)}
        onOpenSettings={() => setActiveTab('settings')}
      />

      {/* App Body with Sidebar & Content */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          isCollapsed={isSidebarCollapsed}
          setIsCollapsed={setIsSidebarCollapsed}
        />

        <main className="flex-1 min-h-0 min-w-0 flex overflow-hidden bg-white">
          {activeTab === 'board' && <KanbanScrumBoard />}
          {activeTab === 'backlog' && <BacklogView />}
          {activeTab === 'problems' && (
            <div
              data-testid="problem-archive-scroll"
              className="flex-1 min-h-0 min-w-0 h-full bg-[#1c1c1c] text-white overflow-auto"
            >
              <ProblemList
                onSelectProblem={handleSelectProblemFromList}
                onOpenStory={openIssueDetail}
                onCreateStory={handleCreateStoryForProblem}
                refreshKey={refreshKey}
              />
            </div>
          )}
          {activeTab === 'studyset' && (
            <StudySetApp
              initialStudySetId={activeStudySetId}
              onOpenStory={openIssueDetail}
              projectId={currentProject?.id}
            />
          )}
          {activeTab === 'timeline' && <TimelineGanttView />}
          {activeTab === 'crossteam' && <CrossTeamPlanView />}
          {activeTab === 'releases' && <ReleasesView />}
          {activeTab === 'burndown' && <SprintBurndownView />}
          {activeTab === 'dashboard' && <DashboardView />}
          {activeTab === 'filters' && <IssuesFilterView />}
          {activeTab === 'settings' && <ProjectSettingsView />}
          {activeTab === 'metrics' && <MetricsView />}
          {activeTab === 'ai' && <AiAssistantView />}
        </main>
      </div>

      {/* Global Modals */}
      <GlobalSearchModal isOpen={isSearchOpen} onClose={() => setIsSearchOpen(false)} />
      <CreateIssueModal />
      <IssueDetailModal onOpenProblem={handleSelectProblemFromList} />
      <ImportStoriesModal isOpen={isImportStoriesOpen} onClose={closeImportStories} />
      <AiStoryModal isOpen={isAiStoryOpen} onClose={closeAiStory} />
      <LoadStudySetModal
        isOpen={isLoadStudySetOpen}
        onClose={closeLoadStudySet}
        onSelectStudySet={(id) => {
          setActiveStudySetId(id);
          setActiveTab('studyset');
        }}
        onOpenStory={(storyId) => {
          closeLoadStudySet();
          openIssueDetail(storyId);
        }}
        projectId={currentProject?.id}
      />

      {/* Extensible Activity Screen */}
      {activeActivityIssue && (
        <ActivityScreen
          issue={activeActivityIssue}
          onClose={closeActivity}
          onOpenStory={(issueId) => {
            closeActivity();
            openIssueDetail(issueId);
          }}
          onCreateStory={async (problemId) => {
            const story = await handleCreateStoryForProblem(problemId);
            closeActivity();
            openIssueDetail(story.id);
          }}
          onStatusUpdated={handleActivityStatusUpdated}
        />
      )}
    </div>
  );
};

export const App = () => {
  return (
    <AuthProvider>
      <ProjectProvider>
        <MainApp />
      </ProjectProvider>
    </AuthProvider>
  );
};

export default App;
