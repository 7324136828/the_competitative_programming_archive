export async function navigateToLinkedStudySet(studySetId, targetTab, activate, navigate) {
  if (!studySetId) {
    throw new Error('No study set is linked to this story.');
  }

  let workspace;
  try {
    workspace = await activate(studySetId);
  } catch (error) {
    if (/not found|404/i.test(error?.message || '')) {
      throw new Error('The linked study set is unavailable. It may have been deleted.');
    }
    throw new Error(`Could not open the linked study set: ${error?.message || 'Please try again.'}`);
  }

  if (workspace?.activeWorkspace !== studySetId) {
    throw new Error('The linked study set could not be activated. Please try again.');
  }

  navigate(studySetId, targetTab);
}
