import React, { useState, useEffect, useMemo, useRef } from 'react';
import "./adminreview.css"

export default function AdminReviewPage({ adminUsername }) {
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [documents, setDocuments] = useState([]);
  
  const [currentDocument, setCurrentDocument] = useState(null);
  const [adminCorrectedJson, setAdminCorrectedJson] = useState(null);
  const [jsonError, setJsonError] = useState('');

  const [loading, setLoading] = useState({
    users: false,
    projects: false,
    documents: false,
    action: false,
  });
  const [error, setError] = useState('');

  const textareaRef = useRef(null);

  useEffect(() => {
    fetchUsers();
  }, []);

  useEffect(() => {
    if (selectedUser) {
      fetchProjectsForUser(selectedUser);
    }
  }, [selectedUser]);

  useEffect(() => {
    if (selectedUser && selectedProject) {
      fetchCorrectedDocuments(selectedUser, selectedProject);
    }
  }, [selectedUser, selectedProject]);

  useEffect(() => {
    if (currentDocument) {
      setAdminCorrectedJson(JSON.parse(JSON.stringify(currentDocument.corrected_json)));
      setJsonError('');
    }
  }, [currentDocument]);

  const updateLoading = (key, value) => setLoading(prev => ({ ...prev, [key]: value }));
  
  async function fetchUsers() {
    updateLoading('users', true);
    try {
      const response = await fetch('/api/admin/get_users');
      const data = await response.json();
      if (response.ok) {
        setUsers(data.users || []);
      } else {
        throw new Error(data.error || 'Failed to fetch users');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      updateLoading('users', false);
    }
  }

  async function fetchProjectsForUser(username) {
    updateLoading('projects', true);
    setProjects([]);
    setSelectedProject(null);
    setDocuments([]);
    try {
      const response = await fetch(`/api/admin/get_user_projects?username=${username}`);
      const data = await response.json();
      if (response.ok) {
        setProjects(data.projects || []);
      } else {
        throw new Error(data.error || 'Failed to fetch projects');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      updateLoading('projects', false);
    }
  }

  async function fetchCorrectedDocuments(username, projectName) {
    updateLoading('documents', true);
    setDocuments([]);
    try {
      const response = await fetch(`/api/admin/get_corrected_documents?username=${username}&project_name=${projectName}`);
      const data = await response.json();
      if (response.ok) {
        setDocuments(data.documents || []);
      } else {
        throw new Error(data.error || 'Failed to fetch documents');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      updateLoading('documents', false);
    }
  }

  const handleUserSelect = (username) => {
    setSelectedUser(username);
    setSelectedProject(null);
    setDocuments([]);
  };
  
  const handleProjectSelect = (projectName) => {
    setSelectedProject(projectName);
  };
  
  const handleJsonEdit = (e) => {
    const newJsonString = e.target.value;
    try {
      JSON.parse(newJsonString);
      setJsonError('');
    } catch (err) {
      setJsonError('Invalid JSON format.');
    }
    setAdminCorrectedJson(newJsonString); 
  };
  
  const handleReviewAction = async (action) => {
    if (!currentDocument || jsonError) {
      alert('Cannot proceed: Document not selected or JSON is invalid.');
      return;
    }
    updateLoading('action', true);

    let finalCorrectedJson;
    try {
        finalCorrectedJson = (typeof adminCorrectedJson === 'string') 
            ? JSON.parse(adminCorrectedJson) 
            : adminCorrectedJson;
    } catch (e) {
        alert('Cannot approve with invalid JSON.');
        updateLoading('action', false);
        return;
    }
    
    const payload = {
      project_name: selectedProject,
      document_id: currentDocument.id,
      action: action,
      admin_username: adminUsername,
      ...(action === 'approve' && { corrected_json: finalCorrectedJson }),
    };

    try {
      const response = await fetch('/api/admin/review_correction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();

      if (response.ok) {
        alert(`Document successfully ${action}ed.`);
        setDocuments(prev => prev.filter(doc => doc.id !== currentDocument.id));
        setCurrentDocument(null);
      } else {
        throw new Error(data.error || `Failed to ${action} document.`);
      }
    } catch (err) {
      setError(err.message);
      alert(err.message);
    } finally {
      updateLoading('action', false);
    }
  };
  
  const handleLogItemClick = (log) => {
    if (!textareaRef.current) return;
    const textarea = textareaRef.current;
    const text = textarea.value;
    const parts = log.field.split('.');
    
    let searchStartIndex = 0;

    for (let i = 0; i < parts.length; i++) {
        const isLastPart = i === parts.length - 1;
        const part = parts[i];
        const keyMatch = part.match(/(\w+)/);
        if (!keyMatch) return;
        const key = keyMatch[0];
        const keyIndex = text.indexOf(`"${key}":`, searchStartIndex);
        
        if (keyIndex === -1) return;

        if (isLastPart) {
            textarea.focus();
            const lineEndIndex = text.indexOf('\n', keyIndex);
            const selectionEnd = lineEndIndex > -1 ? lineEndIndex : text.length;
            textarea.setSelectionRange(keyIndex, selectionEnd);

            const textBefore = text.substring(0, keyIndex);
            const lineNumber = textBefore.split('\n').length;
            const lineHeight = 18;
            const desiredScrollTop = (lineNumber * lineHeight) - (textarea.clientHeight / 2);
            textarea.scrollTop = Math.max(0, desiredScrollTop);
            return;
        }

        searchStartIndex = keyIndex + key.length;
        const arrayMatch = part.match(/\[(\d+)\]/);

        if (arrayMatch) {
            const n = parseInt(arrayMatch[1], 10);
            const arrayStartIndex = text.indexOf('[', searchStartIndex);
            if (arrayStartIndex === -1) return;
            
            let cursor = arrayStartIndex + 1;
            let elementsToSkip = n;
            
            while (elementsToSkip > 0) {
                let nestingLevel = 0;
                let foundSeparator = false;
                for (let j = cursor; j < text.length; j++) {
                    const char = text[j];
                    if (char === '{' || char === '[') nestingLevel++;
                    else if (char === '}' || char === ']') nestingLevel--;
                    else if (char === ',' && nestingLevel === 0) {
                        cursor = j + 1;
                        elementsToSkip--;
                        foundSeparator = true;
                        break;
                    } else if (char === ']' && nestingLevel < 0) {
                        return;
                    }
                }
                if (!foundSeparator) return;
            }
            searchStartIndex = cursor;
        }
    }
  };

  const renderJsonField = (obj) => {
    if (typeof obj !== 'object' || obj === null) {
      return (
        <span className="json-value">
          {typeof obj === 'string' ? `"${obj}"` : String(obj)}
        </span>
      );
    }

    if (Array.isArray(obj)) {
      return (
        <div className="json-array">
          [
          {obj.map((item, index) => (
            <div key={index} className="json-array-item">
              {renderJsonField(item)}
              {index < obj.length - 1 && ','}
            </div>
          ))}
          ]
        </div>
      );
    }

    return (
      <div className="json-object">
        {'{'}
        {Object.entries(obj).map(([key, value], index, arr) => {
          return (
            <div key={key} className="json-field">
              <span className="json-key">"{key}"</span>
              : {renderJsonField(value)}
              {index < arr.length - 1 && ','}
            </div>
          );
        })}
        {'}'}
      </div>
    );
  };
  
  const memoizedUserCorrection = useMemo(() => {
    if (!currentDocument) return null;
    return renderJsonField(currentDocument.corrected_json);
  }, [currentDocument]);

  if (currentDocument) {
    return (
      <div className="admin-review-page review-mode">
        <div className="review-header">
          <button onClick={() => setCurrentDocument(null)} className="back-button">
            &larr; Back to Document List
          </button>
          <h2>Reviewing Document ID: {currentDocument.id}</h2>
          <p>Corrected by: <strong>{currentDocument.corrected_by}</strong> in project <strong>{selectedProject}</strong></p>
        </div>
        
        <div className="review-interface">
          <div className="review-panel source-panel">
            <h3>Source Text</h3>
            <div className="source-text-container">
              {currentDocument.text}
            </div>
          </div>

          <div className="review-panel comparison-panel">
            <h3>User's Correction & Log</h3>
            <div className="user-correction-json">
              <h4>Corrected JSON</h4>
              <div className="json-container">
                {memoizedUserCorrection}
              </div>
            </div>
            <div className="user-correction-log">
              <h4>Correction Log ({currentDocument.correction_log?.length || 0})</h4>
              <div className="log-items-container">
                {currentDocument.correction_log && currentDocument.correction_log.length > 0 ? (
                  currentDocument.correction_log.map((log, index) => (
                    <div 
                      key={index} 
                      className="log-item log-item-clickable"
                      onClick={() => handleLogItemClick(log)}
                    >
                      <strong>{log.field}</strong> ({log.error_type})
                      <div className="log-change">
                         {log.is_new_field 
                          ? `Added: "${log.corrected_value}"`
                          : `"${log.original_value}" → "${log.corrected_value}"`
                         }
                      </div>
                      {log.evidence && <div className="log-evidence">Evidence: "{log.evidence}"</div>}
                    </div>
                  ))
                ) : (
                  <p className="log-item">No corrections logged. User marked as correct.</p>
                )}
              </div>
            </div>
          </div>
          
          <div className="review-panel admin-action-panel">
            <h3>Admin Correction & Actions</h3>
            <div className="admin-json-editor">
              <h4>Edit JSON (and Approve)</h4>
              <textarea
                ref={textareaRef}
                value={typeof adminCorrectedJson === 'string' ? adminCorrectedJson : JSON.stringify(adminCorrectedJson, null, 2)}
                onChange={handleJsonEdit}
                className={`json-textarea ${jsonError ? 'has-error' : ''}`}
              />
              {jsonError && <p className="json-error-message">{jsonError}</p>}
            </div>
            <div className="admin-action-buttons">
              <button
                className="action-button approve-button"
                onClick={() => handleReviewAction('approve')}
                disabled={loading.action || !!jsonError}
              >
                {loading.action ? 'Approving...' : 'Correct & Approve'}
              </button>
              <button
                className="action-button reject-button"
                onClick={() => handleReviewAction('reject')}
                disabled={loading.action}
              >
                {loading.action ? 'Rejecting...' : 'Reject Correction'}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  } else {
    return (
      <div className="admin-review-page selection-mode">
        <h1 className="page-title">Admin Review Dashboard</h1>
        {error && <div className="error-banner">{error}</div>}
        <div className="selection-container">
          <div className="selection-column">
            <h2 className="column-header">1. Select User</h2>
            <div className="item-list user-list">
              {loading.users ? <p>Loading users...</p> : 
                users.map(user => (
                  <div
                    key={user}
                    className={`list-item ${selectedUser === user ? 'selected' : ''}`}
                    onClick={() => handleUserSelect(user)}
                  >
                    {user}
                  </div>
                ))
              }
            </div>
          </div>
          <div className="selection-column">
            <h2 className="column-header">2. Select Project</h2>
            {selectedUser && (
              <div className="item-list project-list">
                {loading.projects ? <p>Loading projects...</p> : 
                  projects.length > 0 ? projects.map(proj => (
                    <div
                      key={proj}
                      className={`list-item ${selectedProject === proj ? 'selected' : ''}`}
                      onClick={() => handleProjectSelect(proj)}
                    >
                      {proj}
                    </div>
                  )) : <p>No projects found for this user.</p>
                }
              </div>
            )}
          </div>
          <div className="selection-column">
            <h2 className="column-header">3. Select Document to Review</h2>
            {selectedProject && (
              <div className="item-list document-list">
                {loading.documents ? <p>Loading documents...</p> : 
                  documents.length > 0 ? documents.map(doc => (
                    <div
                      key={doc.id}
                      className="list-item document-item"
                      onClick={() => setCurrentDocument(doc)}
                    >
                      <span className="doc-id">ID: {doc.id}</span>
                      <span className="doc-timestamp">
                        Corrected: {new Date(doc.corrected_at).toLocaleString()}
                      </span>
                    </div>
                  )) : <p>No documents to review for this user/project.</p>
                }
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }
}